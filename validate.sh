#!/bin/bash

if [ $# -eq 0 ]; then
    echo "Running validate.yaml on all hosts"
    ansible-playbook validate.yaml
else
    echo "Running validate.yaml on $1"
    ansible-playbook -i "$1," validate.yaml
fi
