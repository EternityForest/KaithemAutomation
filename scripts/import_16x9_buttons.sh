#!/bin/bash
set -e
button_images_source="button_images_pack/src"
mkdir -p button_images_pack/src
mkdir -p button_images_pack/output

for file in $button_images_source/*.jpg; do
    filename=$(basename "$file")
    output_file="button_images_pack/output/${filename%.jpg}.avif"
    im_file="button_images_pack/output/${filename}"

    convert "$file" -resize 240x "$im_file"
    convert "$im_file" -liquid-rescale 240x135\! "$output_file"
    rm "$im_file"
done