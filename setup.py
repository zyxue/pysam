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

IS_PYTHON3 = sys.version_info.major >= 3


@contextmanager
def changedir(path):
    save_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(save_dir)


def configure_library(library_dir, env_options=None, options=[]):

    configure_script = os.path.join(library_dir, "configure")

    if not os.path.exists(configure_script):
        raise ValueError(
            "configure script {} does not exist".format(configure_script))

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

    with changedir(library_dir):
        if env_options is not None:
            if run_configure(env_options):
                return env_options

        for option in options:
            if run_configure(option):
                return option
    return None


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
HTSLIB_MODE = "shared"
HTSLIB_LIBRARY_DIR = os.environ.get("HTSLIB_LIBRARY_DIR", None)
HTSLIB_INCLUDE_DIR = os.environ.get("HTSLIB_INCLUDE_DIR", None)
HTSLIB_CONFIGURE_OPTIONS = os.environ.get("HTSLIB_CONFIGURE_OPTIONS", None)

# Check if cython is available
#
# If cython is available, the pysam will be built using cython from
# the .pyx files. If no cython is available, the C-files included in the
# distribution will be used.
try:
    from cy_build import CyExtension as Extension, cy_build_ext as build_ext
    source_pattern = "pysam/c%s.pyx"
    cmdclass = {'build_ext': build_ext}
    HTSLIB_MODE = "shared"
except ImportError:
    # no Cython available - use existing C code
    cmdclass = {}
    source_pattern = "pysam/c%s.c"
    # Set mode to separate, as "shared" not fully tested yet.
    HTSLIB_MODE = "separate"

# collect pysam version
sys.path.insert(0, "pysam")
import version
version = version.__version__

# exclude sources that contain a main function
EXCLUDE = {
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
        'reheader.c',  # needs to renamed, name conflict with samtools reheader
        'test'
    ),

    "htslib": (
        'htslib/bgzip.c',
        'htslib/hfile_irods.c',
        'htslib/htsfile.c',
        'htslib/tabix.c'
    )
}

if __name__ == '__main__':
    dist = setup(**metadata)
