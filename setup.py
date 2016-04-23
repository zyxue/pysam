#! /usr/bin/python

'''pysam - a python module for reading, manipulating and writing
genomic data sets.

pysam is a lightweight wrapper of the htslib C-API and provides
facilities to read and write SAM/BAM/VCF/BCF/BED/GFF/GTF/FASTA/FASTQ
files as well as access to the command line functionality of the
samtools and bcftools packages. The module supports compression and
random access through indexing.

This module provides a low-level wrapper around the htslib C-API as
using cython and a high-level API for convenient access to the data
within standard genomic file formats.

The current version wraps htslib-1.3, samtools-1.3 and bcftools-1.3.

See:
http://www.htslib.org
https://github.com/pysam-developers/pysam
http://pysam.readthedocs.org/en/stable

'''

import collections
import glob
import os
import platform
import re
import subprocess
import sys
from contextlib import contextmanager
from setuptools import Extension, setup

import logging
logging.basicConfig(
    level=logging.DEBUG, format='%(asctime)s|%(levelname)s|%(message)s')

IS_PYTHON3 = sys.version_info.major >= 3


@contextmanager
def changedir(path):
    save_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(save_dir)


def run_configure(option):
    try:
        retcode = subprocess.call(
            " ".join(("./configure", option)),
            shell=True)
        if retcode != 0:
            return False
        else:
            return True
    except OSError as e:
        return False


def configure_library(library_dir, env_options=None, options=[]):
    configure_script = os.path.join(library_dir, "configure")

    if not os.path.exists(configure_script):
        raise ValueError(
            "configure script {} does not exist".format(configure_script))

    with changedir(library_dir):
        if env_options is not None:
            if run_configure(env_options):
                return env_options

        for option in options:
            if run_configure(option):
                return option
    return None


def check_cython():
    # Check if cython is available
    #
    # If cython is available, the pysam will be built using cython from
    # the .pyx files. If no cython is available, the C-files included in the
    # distribution will be used.
    try:
        from cy_build import CyExtension as Extension, cy_build_ext as build_ext
        source_pattern = "pysam/c%s.pyx"
        cmdclass = {'build_ext': build_ext}
        htslib_mode = "shared"
        logging.info('cython found. use HTSLIB_MODE: {0}'.format(HTSLIB_MODE))
    except ImportError:
        # no Cython available - use existing C code
        cmdclass = {}
        source_pattern = "pysam/c%s.c"
        # Set mode to separate, as "shared" not fully tested yet.
        htslib_mode = "separate"
        logging.warning(
            'cython not installed. use HTSLIB_MODE: {0}'.format(HTSLIB_MODE))
    return source_pattern, cmdclass, htslib_mode


def check_version():
    # collect pysam version
    sys.path.insert(0, "pysam")
    import version
    version = version.__version__
    logging.info('pysam version: {0}'.format(version))
    return version


def get_exclude():
    # exclude sources that contain a main function
    return {
        "samtools": (
            'bam2bed.c',
            'bamcheck.c',
            'bgzip.c',
            'calDepth.c',
            'chk_indel.c',
            'hfile_irods.c',        # requires irods library
            'htslib-1.3',           # do not import twice
            'main.c',
            'maq2sam.c',
            'md5fa.c',
            'md5sum-lite.c',
            'razip.c',
            'vcf-miniview.c',
            'wgsim.c'
        ),

        "bcftools": (
            'peakfit.c',
            'peakfit.h',
            'plugins',
            'polysomy.c',
            # needs to renamed, name conflict with samtools reheader
            'reheader.c',
            'test'
        ),

        "htslib": (
            'htslib/bgzip.c',
            'htslib/hfile_irods.c',
            'htslib/htsfile.c',
            'htslib/tabix.c'
        )
    }


def get_htslib_source(htslib_mode):
    if htslib_mode in ['shared', 'separate']:
        return 'builtin'
    else:
        return ''


def update_htslib_configure_options(htslib_mode, htslib_configure_options):
    if htslib_mode in ['shared', 'separate']:
        options = configure_library(
            "htslib",
            htslib_configure_options,
            ["--enable-libcurl"])

        logging.info("htslib configure options: {}".format(str(options)))

        if options is None:
            # create empty config.h file
            with open("htslib/config.h", "w") as outf:
                outf.write("/* empty config.h created by pysam */\n")
                outf.write("/* conservative compilation options */\n")
    return options


def get_internal_htslib_libraries_for_shared(is_python3):
    if is_python3:
        import sysconfig
        if sys.version_info.minor >= 5:
            internal_htslib_libraries = ["chtslib.{}".format(
                sysconfig.get_config_var('SOABI'))]
        else:
            if sys.platform == "darwin":
                # On OSX, python 3.3 and 3.4 Libs have no platform tags.
                internal_htslib_libraries = ["chtslib"]
            else:
                internal_htslib_libraries = ["chtslib.{}{}".format(
                    sys.implementation.cache_tag,
                    sys.abiflags)]
    else:
        internal_htslib_libraries = ["chtslib"]
    return internal_htslib_libraries


def gen_htslib_vars(htslib_library_dir,
                    htslib_include_dir,
                    htslib_mode,
                    is_python3):
    """
    generate the following htslib related variables:
        htslib_sources
        shared_htslib_sources
        chtslib_sources
        htslib_library_dirs
        htslib_include_dirs
        internal_htslib_libraries
        external_htslib_libraries
    """
    if htslib_library_dir:
        # linking against a shared, externally installed htslib version, no
        # sources required for htslib
        return ([], [], [],
                [htslib_library_dir], [htslib_include_dir], [], ['z', 'hts'])

    if htslib_mode == 'separate':
        # add to each pysam component a separately compiled htslib
        htslib_sources = [
            x for x in
            glob.glob(os.path.join("htslib", "*.c")) +
            glob.glob(os.path.join("htslib", "cram", "*.c"))
            if x not in EXCLUDE["htslib"]]
        shared_htslib_sources = htslib_sources
        return (htslib_sources, shared_htslib_sources,
                [], [], ['htslib'], [], ['z'])

    if htslib_mode == 'shared':
        # link each pysam component against the same htslib built from sources
        # included in the pysam package.
        shared_htslib_sources = [
            x for x in
            glob.glob(os.path.join("htslib", "*.c")) +
            glob.glob(os.path.join("htslib", "cram", "*.c"))
            if x not in EXCLUDE["htslib"]]
        internal_lib = get_internal_htslib_libraries_for_shared(is_python3)
        return ([], shared_htslib_sources, [], ['pysam', "."], ['htslib'],
                internal_lib, ['z'])

    raise ValueError("unknown HTSLIB value '%s'" % HTSLIB_MODE)


def build_config(htslib_source):
    # build config.py
    with open(os.path.join("pysam", "config.py"), "w") as outf:
        outf.write('HTSLIB = "{}"\n'.format(HTSLIB_SOURCE))
        config_values = collections.defaultdict(int)

        if htslib_source == "builtin":
            with open(os.path.join("htslib", "config.h")) as inf:
                for line in inf:
                    if line.startswith("#define"):
                        key, value = re.match(
                            "#define (\S+)\s+(\S+)", line).groups()
                        config_values[key] = int(value)
                for key in ["ENABLE_PLUGINS",
                            "HAVE_COMMONCRYPTO",
                            "HAVE_GMTIME_R",
                            "HAVE_HMAC",
                            "HAVE_IRODS",
                            "HAVE_LIBCURL",
                            "HAVE_MMAP"]:
                    outf.write("{} = {}\n".format(key, config_values[key]))


# How to link against HTSLIB
# separate: use included htslib and include in each extension
#           module. No dependencies between modules and works
#           with setup.py install, but wasteful in terms of
#           memory and compilation time.
# shared: share chtslib across extension modules. This would be
#         the ideal method, but currently requires
#         LD_LIBRARY_PATH to be set correctly when using
#         pysam.
# external: use shared libhts.so compiled outside of
#           pysam
HTSLIB_LIBRARY_DIR = os.environ.get("HTSLIB_LIBRARY_DIR", None)
HTSLIB_INCLUDE_DIR = os.environ.get("HTSLIB_INCLUDE_DIR", None)
HTSLIB_CONFIGURE_OPTIONS = os.environ.get("HTSLIB_CONFIGURE_OPTIONS", None)

source_pattern, cmdclass, HTSLIB_MODE = check_cython()
version = check_version()
EXCLUDE = get_exclude()

htslib_configure_options = None
HTSLIB_SOURCE = get_htslib_source(HTSLIB_MODE)
htslib_configure_options = update_htslib_configure_options(
    HTSLIB_MODE, HTSLIB_CONFIGURE_OPTIONS)


(htslib_sources,
 shared_htslib_sources,
 chtslib_sources,
 htslib_library_dirs,
 htslib_include_dirs,
 internal_htslib_libraries,
 external_htslib_libraries) = gen_htslib_vars(HTSLIB_LIBRARY_DIR,
                                              HTSLIB_INCLUDE_DIR,
                                              HTSLIB_MODE,
                                              IS_PYTHON3)

build_config(HTSLIB_SOURCE)


if HTSLIB_SOURCE == "builtin":
    EXCLUDE_HTSLIB = ["htslib/hfile_libcurl.c"]
    if htslib_configure_options is None:
        logging.info("# pysam: could not configure htslib, choosing "
                     "conservative defaults")
        htslib_sources = [x for x in htslib_sources
                          if x not in EXCLUDE_HTSLIB]
        shared_htslib_sources = [x for x in shared_htslib_sources
                                 if x not in EXCLUDE_HTSLIB]
    elif "--disable-libcurl" in htslib_configure_options:
        logging.info("# pysam: libcurl has been disabled")
        htslib_sources = [x for x in htslib_sources
                          if x not in EXCLUDE_HTSLIB]
        shared_htslib_sources = [x for x in shared_htslib_sources
                                 if x not in EXCLUDE_HTSLIB]
    elif "--enable-libcurl" in htslib_configure_options:
        logging.info("# pysam: libcurl of builtin htslib has been enabled, "
                     "adding shared libcurl and libcrypto")
        external_htslib_libraries.extend(["curl", "crypto"])

# create empty config.h files if they have not been created automatically
# or created by the user:
for fn in "samtools/config.h", "htslib/config.h":
    if not os.path.exists(fn):
        with open(fn, "w") as outf:
            outf.write("/* empty config.h created by pysam */\n")
            outf.write("/* conservative compilation options */\n")

parts = ["samtools",
         "bcftools",
         "htslib",
         "tabix",
         "faidx",
         "samfile",
         "utils",
         "alignmentfile",
         "tabixproxies",
         "vcf",
         "bcf"]

# remove existing files to recompute
# necessary to be both compatible for python 2.7 and 3.3
if IS_PYTHON3:
    for part in parts:
        try:
            os.unlink("pysam/c%s.c" % part)
        except:
            pass

# Exit if there are no pre-compiled files and no cython available
fn = source_pattern % "htslib"
if not os.path.exists(fn):
    raise ValueError(
        "no cython installed, but can not find {}."
        "Make sure that cython is installed when building "
        "from the repository"
        .format(fn))


#######################################################
classifiers = """
Development Status :: 3 - Beta
Operating System :: MacOS :: MacOS X
Operating System :: POSIX
Operating System :: POSIX :: Linux
Operating System :: Unix
Programming Language :: Python
Topic :: Scientific/Engineering
Topic :: Scientific/Engineering :: Bioinformatics
"""

#######################################################

#######################################################
# Windows compatibility - untested
if platform.system() == 'Windows':
    include_os = ['win32']
    os_c_files = ['win32/getopt.c']
    extra_compile_args = []
else:
    include_os = []
    os_c_files = []
    # for python 3.4, see for example
    # http://stackoverflow.com/questions/25587039/
    # error-compiling-rpy2-on-python3-4-due-to-werror-
    # declaration-after-statement
    extra_compile_args = [
        "-Wno-unused",
        "-Wno-strict-prototypes",
        "-Wno-sign-compare",
        "-Wno-error=declaration-after-statement"]

define_macros = []

chtslib = Extension(
    "pysam.libchtslib",
    [source_pattern % "htslib",
     "pysam/htslib_util.c"] +
    shared_htslib_sources +
    os_c_files,
    library_dirs=htslib_library_dirs,
    runtime_library_dirs=htslib_library_dirs,
    include_dirs=["pysam", "."] + include_os + htslib_include_dirs,
    libraries=external_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

# samfile requires functions defined in bam_md.c
# for __advance_samtools method.
# Selected ones have been copied into samfile_utils.c
# Needs to be devolved somehow.
csamfile = Extension(
    "pysam.csamfile",
    [source_pattern % "samfile",
     "pysam/htslib_util.c",
     "pysam/samfile_util.c",
     "samtools/kprobaln.c"] +
    htslib_sources +
    os_c_files,
    library_dirs=htslib_library_dirs,
    include_dirs=["pysam", "samtools", "."] + include_os + htslib_include_dirs,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

# alignmentfile requires functions defined in bam_md.c
# for __advance_samtools method.
# Selected ones have been copied into samfile_utils.c
# Needs to be devolved somehow.
calignmentfile = Extension(
    "pysam.calignmentfile",
    [source_pattern % "alignmentfile",
     "pysam/htslib_util.c",
     "pysam/samfile_util.c",
     "samtools/kprobaln.c"] +
    htslib_sources +
    os_c_files,
    library_dirs=htslib_library_dirs,
    include_dirs=["pysam", "samtools"] + include_os + htslib_include_dirs,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

# alignmentfile requires functions defined in bam_md.c
# for __advance_samtools method.
# Selected ones have been copied into samfile_utils.c
# Needs to be devolved somehow.
calignedsegment = Extension(
    "pysam.calignedsegment",
    [source_pattern % "alignedsegment",
     "pysam/htslib_util.c",
     "pysam/samfile_util.c",
     "samtools/kprobaln.c"] +
    htslib_sources +
    os_c_files,
    library_dirs=htslib_library_dirs,
    include_dirs=["pysam", "samtools", "."] + include_os + htslib_include_dirs,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

ctabix = Extension(
    "pysam.ctabix",
    [source_pattern % "tabix",
     "pysam/tabix_util.c"] +
    htslib_sources +
    os_c_files,
    library_dirs=["pysam"] + htslib_library_dirs,
    include_dirs=["pysam", "."] + include_os + htslib_include_dirs,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

cutils = Extension(
    "pysam.cutils",
    [source_pattern % "utils", "pysam/pysam_util.c"] +
    glob.glob(os.path.join("samtools", "*.pysam.c")) +
    # glob.glob(os.path.join("samtools", "*", "*.pysam.c")) +
    glob.glob(os.path.join("bcftools", "*.pysam.c")) +
    # glob.glob(os.path.join("bcftools", "*", "*.pysam.c")) +
    htslib_sources +
    os_c_files,
    library_dirs=["pysam"] + htslib_library_dirs,
    include_dirs=["samtools", "bcftools", "pysam", "."] +
    include_os + htslib_include_dirs,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

cfaidx = Extension(
    "pysam.cfaidx",
    [source_pattern % "faidx"] +
    htslib_sources +
    os_c_files,
    library_dirs=["pysam"] + htslib_library_dirs,
    include_dirs=["pysam", "."] + include_os + htslib_include_dirs,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

ctabixproxies = Extension(
    "pysam.ctabixproxies",
    [source_pattern % "tabixproxies"] +
    os_c_files,
    library_dirs=htslib_library_dirs,
    include_dirs=include_os,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

cvcf = Extension(
    "pysam.cvcf",
    [source_pattern % "vcf"] +
    os_c_files,
    library_dirs=htslib_library_dirs,
    include_dirs=["htslib", "."] + include_os + htslib_include_dirs,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

cbcf = Extension(
    "pysam.cbcf",
    [source_pattern % "bcf"] +
    htslib_sources +
    os_c_files,
    library_dirs=htslib_library_dirs,
    include_dirs=["htslib", "."] + include_os + htslib_include_dirs,
    libraries=external_htslib_libraries + internal_htslib_libraries,
    language="c",
    extra_compile_args=extra_compile_args,
    define_macros=define_macros
)

metadata = {
    'name': "pysam",
    'version': version,
    'description': "pysam",
    'long_description': __doc__,
    'author': "Andreas Heger",
    'author_email': "andreas.heger@gmail.com",
    'license': "MIT",
    'platforms': "ALL",
    'url': "https://github.com/pysam-developers/pysam",
    'packages': ['pysam',
                 'pysam.include',
                 'pysam.include.htslib',
                 'pysam.include.htslib.htslib',
                 'pysam.include.samtools',
                 'pysam.include.bcftools',
                 'pysam.include.samtools.win32'],
    'requires': ['cython (>=0.21)'],
    'ext_modules': [chtslib,
                    csamfile,
                    calignmentfile,
                    calignedsegment,
                    ctabix,
                    ctabixproxies,
                    cvcf,
                    cbcf,
                    cfaidx,
                    cutils],
    'cmdclass': cmdclass,
    'package_dir': {'pysam': 'pysam',
                    'pysam.include.htslib': 'htslib',
                    'pysam.include.samtools': 'samtools',
                    'pysam.include.bcftools': 'bcftools'},
    'package_data': {'': ['*.pxd', '*.h'], },
    # do not pack in order to permit linking to csamtools.so
    'zip_safe': False,
    'use_2to3': True,
}

if __name__ == '__main__':
    dist = setup(**metadata)
