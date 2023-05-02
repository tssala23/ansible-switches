#!/bin/bash

# ! TODO - write a way to parse methods so that --diff and --check can be passed through

if [ $# -eq 0 ]; then
    echo "Running site.yaml on all hosts"
    ansible-playbook site.yaml
else
    echo "Running site.yaml on $1"
    ansible-playbook -i "$1," site.yaml
fi
