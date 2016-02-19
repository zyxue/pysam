#!/bin/bash
set -e

if [[ $TRAVIS_OS_NAME = "linux" ]]
then
    ./run_tests_travis.sh
else
    export PATH=/anaconda/bin:$PATH
    # build packages
    # scripts/build-packages.py --repository . --packages `cat osx-whitelist.txt`
fi
