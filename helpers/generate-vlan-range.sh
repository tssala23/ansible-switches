#!/bin/bash

range_start=$1
range_end=$2
name=$3
desc=$4

for i in $(seq $range_start $range_end); do
    echo "$i:"
    echo "  name: ${name}-$i"
    echo "  description: ${desc} $i"
done
