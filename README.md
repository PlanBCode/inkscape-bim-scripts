# Inkscape BIM scripts

This repository contains a number of scripts that assist in using an
inkscape SVG file as a BIM (Building Information Management) system.

The idea is to add various annotations (room numbers, room use,
electrical outlets and circuits, etc.) to separate layers in an SVG, on
top of some floorplan (manually drawn or imported from elsewhere). These
scripts then allow:

 - Generating PDFs from such an SVG file, with different pages of
   different files composed of different combinations of layers from the
   SVG file.
 - Generating lists of electrical circuits from the SVG floorplan
   annotations.

The overarching idea is that the floorplan SVG file creates a single
source of truth, a sort of visual database, which can then be used to
generate various other artifacts.

## Dependencies and running

To install dependencies into an automatically created virtualenv, you
can use the poetry tool. From within the repository root, run:

    poetry install

Then to run scripts use `poetry shell` to load the virtualenv and then
run the scripts, or combine both using e.g.:

    poetry run ./scripts/export_layers.py

## License

All code in this repository is licensed under the MIT license. See
comments in the individual files for the full copyright notices and
license text.
