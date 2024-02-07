#!/usr/bin/env python3

# Based on https://github.com/hfichtenberger/inkscape-export-overlays
#
# Copyright (c) 2016 "Jesús Espino and Xavier Julian"
# Copyright (c) 2018 Hendrik Fichtenberger
# Copyright (c) 2021 Matthijs Kooijman
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# This script generates multiple PDF outputs from a single SVG
# floorplan, selecting different combinations of layers for different
# pages of different output files, based on configuration.

import argparse
import copy
import datetime
import pathlib
import subprocess
import sys
import tempfile

sys.path.append('/usr/share/inkscape/extensions')
import inkex


# Add a Mask object, which seems to be missing from inkex. It's just a simple
# container like ClipPath
class Mask(inkex.elements._groups.GroupBase):
    """A path used to mask objects"""
    tag_name = 'mask'


class LayerSetExport(inkex.Effect):
    def __init__(self):
        inkex.Effect.__init__(self)
        self.arg_parser.add_argument("--config", action="store", dest="config",
                                     help="Config file that defines what export files to make."
                                     + "Defaults to .cfg.py file matching input SVG file.")
        self.arg_parser.add_argument("--path", action="store", dest="path", default="export", help="")
        self.arg_parser.add_argument("--only", action="store", type=str, dest="only", default="",
                                     help="Only generate files whose filename contains the given string")
        self.arg_parser.add_argument("--keep-svgs", action="store_true",
                                     help="Keep SVGs generated for each page")

        # Hide default inkscape options that we do not need
        for action in self.arg_parser._actions:
            if action.dest in ['selected_nodes']:
                action.help = argparse.SUPPRESS

    def load_config(self, path):
        prompt = f"About to execute {path} to read config, continue only if this file is trusted.\nContinue Y/n?"
        if input(prompt) not in ['', 'y', 'Y']:
            sys.exit(0)
        config = {}
        exec(pathlib.Path(path).read_text(), config)
        return config

    def effect(self):
        output_path = pathlib.Path(self.options.path).expanduser()

        if self.options.config:
            config_path = self.options.config
        else:
            config_path = pathlib.Path(self.options.input_file).with_suffix('.cfg.py')

        config = self.load_config(config_path)
        try:
            outputs = config['EXPORT_LAYERS_OUTPUTS']
        except KeyError:
            print(f"Config file ({config_path}) does not define EXPORT_LAYERS_OUTPUTS variable")
            return

        if self.options.keep_svgs:
            svgdir = output_path / 'svg'
            svgdir.mkdir(parents=True, exist_ok=True)

        for output in outputs:
            if self.options.only and self.options.only not in output['filename']:
                continue
            with tempfile.TemporaryDirectory() as tempdir:
                tempdir = pathlib.Path(tempdir)

                filename = "{} {}".format(datetime.date.today().isoformat(), output['filename'])
                path = output_path / filename
                temp_svg = tempdir / 'page.svg'
                temp_pdfs = []
                print("Exporting {}".format(path))
                for (i, page) in enumerate(output['pages']):
                    print("  Page {}".format(i + 1))

                    if self.options.keep_svgs:
                        temp_svg = svgdir / '{}_page{}.svg'.format(filename, i + 1)

                    texts = output.pop('texts', {})
                    texts.update({
                        'title-block-title': output.get('title', ''),
                        'title-block-subtitle': page.get('subtitle', ''),
                        'title-block-date': datetime.date.today().isoformat(),
                        'title-block-sheet': '{} / {}'.format(i + 1, len(output['pages'])),
                    })

                    self.export_layers(temp_svg, page['layers'], texts, **output)
                    temp_pdf = tempdir / 'page{}.pdf'.format(i + 1)
                    temp_pdfs.append(temp_pdf)

                    self.export_to_pdf(temp_svg, temp_pdf)

                path.parent.mkdir(parents=True, exist_ok=True)
                print(['pdftk', *temp_pdfs, 'cat', 'output', path])
                subprocess.run(['pdftk', *temp_pdfs, 'cat', 'output', path], check=True)

    def export_layers(self, dest, show, texts, page_size=None, transform_layers=(), **kwargs):
        """
        Export selected layers of SVG to the file `dest`.
        :arg  str   dest:  path to export SVG file.
        :arg  list  hide:  layers to hide. each element is a string.
        :arg  list  show:  layers to show. each element is a string.
        """
        doc = copy.deepcopy(self.document)
        svg = doc.getroot()
        if page_size is not None:
            svg.attrib['width'], svg.attrib['height'] = page_size

        transform_dict = {
            layer: {
                'scale': spec.get('scale', None),
                'scale_center': spec.get('scale_center', None),
                'clip_obj': self.make_clip_path(svg, spec['clip']) if 'clip' in spec else None,
                'opacity': spec.get('opacity', None),
            } for spec in transform_layers for layer in spec['layers']
        }

        for layer in doc.xpath('//svg:g[@inkscape:groupmode="layer"]', namespaces=inkex.NSS):
            # TODO: Unhardcode inkscape NS
            label_attr = '{http://www.inkscape.org/namespaces/inkscape}label'
            label = layer.attrib[label_attr]
            if label in show:
                layer.attrib['style'] = 'display:inline'
            else:
                layer.attrib['style'] = 'display:none'

            transform_spec = transform_dict.get(label, None)
            if transform_spec is not None:
                if 'transform' in layer.attrib:
                    raise Exception("Layer {} already has transform, cannot scale".format(label))

                scale = transform_spec['scale']
                if scale:
                    (cx, cy) = transform_spec['scale_center']

                    layer.transform.add_scale(scale)

                    # This effectively moves the layer so (cx, cy) is at the
                    # origin, then scales, then moves back so (cx, cy) ends
                    # up in its original position
                    layer.transform.add_translate(-cx + cx / scale, -cy + cy / scale)

                clip_obj = transform_spec['clip_obj']
                if clip_obj is not None:
                    self.wrap(layer, wrapper=inkex.elements.Layer).clip = clip_obj

                opacity = transform_spec['opacity']
                if opacity is not None:
                    layer.attrib['style'] += ';opacity:{}'.format(opacity)

            # Use masking to fade out everything outside of the working
            # area of a circuit box.
            # TODO: Implement/generalize this once inkscape is fixed: https://gitlab.com/inkscape/inkscape/-/issues/694
            if False and label == 'V0_basistekening':
                # TODO: Rather than hardcoding 0.5 mask for everything
                # else, put a nice gradient that fades out the rest of
                # the building in the mask object?
                kast_mask = self.make_mask(svg, 'mask-elektra-l02-area', 1, 0.5)
                self.apply_mask(layer, kast_mask)

        # TODO: Update metadata data & title?
        for (idattr, value) in texts.items():
            span = svg.getElement('//*[@id="{}"]/svg:tspan'.format(idattr))
            if span is not None:
                span.text = value

        doc.write(dest)

    def make_clip_path(self, svg, obj_id):
        obj = svg.getElementById(obj_id)
        if obj is None:
            return None

        clip = inkex.elements.ClipPath()
        clip.append(obj.copy())
        svg.append(clip)
        return clip

    def make_mask(self, svg, obj_id, opacity, outside_opacity=None):
        obj = svg.getElementById(obj_id)
        mask = Mask()
        if outside_opacity:
            (x, y, w, h) = svg.get_viewbox()
            page_rect = inkex.elements.Rectangle.new(left=x, top=y, width=w, height=h)
            page_rect.style['fill'] = '#ffffff'
            page_rect.style['fill-opacity'] = str(outside_opacity)
            mask.append(page_rect)

        copy = obj.copy()
        copy.style['fill'] = '#ffffff'
        copy.style['fill-opacity'] = str(opacity)
        mask.append(copy)
        svg.append(mask)
        return mask

    def apply_mask(self, obj, mask):
        # Essentially a copy of the inkex.elements.ShapeElement.clip
        # setter, but for mask
        obj.set('mask', mask.get_id(as_url=2))

    def wrap(self, obj, wrapper=inkex.elements.Group):
        wrap = wrapper()
        obj.addprevious(wrap)
        wrap.append(obj)
        return wrap

    def export_to_pdf(self, svg_path, output_path):
        # TODO: Replace with inkex.command.inkscape or inkscape_command?
        area_param = '-C'
        command = "inkscape %s -o \"%s\" \"%s\"" % (area_param, output_path, svg_path)

        PIPE = subprocess.PIPE
        with subprocess.Popen(command.encode("utf-8"), shell=True, stdout=PIPE, stderr=PIPE) as p:
            p.wait()
            p.kill()


def _main():
    e = LayerSetExport()
    e.run()
    exit()


if __name__ == "__main__":
    _main()
