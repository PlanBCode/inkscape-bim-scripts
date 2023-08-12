#!/usr/bin/env python3

# Based on https://github.com/hfichtenberger/inkscape-export-overlays
#
# Copyright (c) 2016 "Jesús Espino and Xavier Julian" # Copyright (c) 2018 Hendrik Fichtenberger
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
import os
import subprocess
import string
import sys
import tempfile

sys.path.append('/usr/share/inkscape/extensions')
import inkex


FLOOR_PAGES = [
    (('V0', 'V00'), 'V0 (begane grond) & kelder'),
    (('V1',), 'V1 (1e verdieping)'),
    (('V2',), 'V2 (2e verdieping)'),
    (('V3',), 'V3 (3e verdieping)'),
]

FLOORS = ('V00', 'V0', 'V1', 'V2', 'V3')

SURFACES = {
    '${floor}_basistekening_oppervlaktes',
}

SHOW_ALWAYS = {
    'Pagina-aankleding', 'Paginarand', 'Paginarand_schaal', 'Titelblok',
    'Gebouwdelen', 'Noordaanduiding', '${floor}',
    '${floor}_basistekening', '${floor}_basistekening_plattegrond',
    '${floor}_basistekening_ruimtenummers',
} | SURFACES

DOOR_NUMBERS = {
    '${floor}_deurnummers', '${floor}_deurnummers_buitendeuren',
}

DIST_BOXES = ('HKL', 'L01', 'L11', 'L21', 'L02', 'L12', 'L001', 'L002', 'L011', 'NV', 'RK1')

# Positions on the bounding box of the floorplan, for scaling into somE
# direction while keeping the same margin on the other side.
FLOORPLAN_TOP_RIGHT = (3818, 365)
# Positions on the inside of the page borders, to allow scaling while
# keeping everything inside the border in view
BORDER_TOP_LEFT = (102, 102)
BORDER_TOP_RIGHT = (4098, 102)

# Center of the ruler in the page border, to allow scaling it along wit
# content scaling
RULER_CENTER = (2100, 2868)


def replace(name, values, layers):
    return {string.Template(layer).safe_substitute({name: value}) for layer in layers for value in values}


def floors(layers):
    return [
        {
            'subtitle': desc,
            'layers': replace('floor', floors, layers),
        } for floors, desc in FLOOR_PAGES
    ]


OUTPUTS = {}

OUTPUTS['Basis'] = [
    {
        'filename': 'Basisplattegrond.pdf',
        'title': 'Plattegrond',
        'pages': floors(SHOW_ALWAYS | DOOR_NUMBERS | {
            '${floor}_basistekening_ruimtegebruik',
            'Wijzigingen ruimtenummers',
        }),
    },
    {
        'filename': 'Ruimtegebruik voor opstalverzekering.pdf',
        'title': 'Ruimtegebruik',
        'pages': floors(SHOW_ALWAYS | DOOR_NUMBERS | {
            '${floor}_basistekening_ruimtegebruik_verzekering',
        }),
    },
]

OUTPUTS['Brandveiligheid'] = [
    {
        'filename': 'Brandveiligheid.pdf',
        'title': 'Brandveiligheid',
        'pages': floors(SHOW_ALWAYS | DOOR_NUMBERS | {
            'Legenda',
            'Legenda_deuren',
            'Legenda_brandscheidingen',
            'Legenda_BMI',
            'Legenda_sluitmechanismen',
            'Legenda_vluchtwegen',
            '${floor}_brandscheidingen',
            '${floor}_basistekening_branddeuren_ramen',
            '${floor}_basistekening_sluitmechanismen',
            '${floor}_installaties',
            '${floor}_installaties_behouden',
            '${floor}_installaties_nieuw',
            '${floor}_installaties_nieuw_later',
            '${floor}_vluchtwegen',
            '${floor}_vluchtwegen_lijnen',
        }),
    },
    {
        'filename': 'Brandwerende doorvoeren.pdf',
        'title': 'Brandwerende doorvoeren',
        'pages': floors(SHOW_ALWAYS | {
            'Legenda',
            'Legenda_deuren',
            'Legenda_brandscheidingen',
            '${floor}_basistekening_branddeuren_ramen',
            '${floor}_brandscheidingen',
            '${floor}_doorvoeren',
        } | replace('BS', ['BS0', 'BS1', 'BS2', 'BS3', 'BS4', 'BS5'], {
            '${floor}_doorvoeren_${BS}',
        })),
    },
    {
        'filename': 'Gebruiksmelding.pdf',
        'title': 'Melding brandveilig gebruik',
        'pages': floors(SHOW_ALWAYS - {'Paginarand_schaal'} | {
            '${floor}_basistekening_bestemming',
            'Legenda',
            'Legenda_deuren',
            'Legenda_brandscheidingen',
            'Legenda_BMI',
            'Legenda_sluitmechanismen',
            'Legenda_vluchtwegen',
            '${floor}_brandscheidingen',
            '${floor}_basistekening_branddeuren_ramen',
            '${floor}_basistekening_sluitmechanismen',
            '${floor}_basistekening_personen',
            '${floor}_basistekening_inrichting',
            '${floor}_installaties',
            '${floor}_installaties_behouden',
            '${floor}_installaties_nieuw',
            '${floor}_installaties_nieuw_later',
            '${floor}_vluchtwegen',
            '${floor}_vluchtwegen_lijnen',
        }),
        'transform_layers': (
            {
                'layers': ('V0', 'V1', 'V2', 'V3', 'V-1', 'Gebouwdelen'),
                'scale': 0.005 / 0.006,  # Convert to 1:200 @ A3
                'scale_center': BORDER_TOP_LEFT,
            },
        ),
        'page_size': ("840mm", "594mm"),  # Convert to 1:100 @ A1
        'texts': {
            'title-block-format': "A1",
            'title-block-scale': "1:100",
            'title-block-altformat': "",
            'title-block-altscale': "",
        }
    },
    {
        'filename': 'Brandmeldinstallatie.pdf',
        'title': 'Brandmeldinstallatie',
        'pages': floors(SHOW_ALWAYS | DOOR_NUMBERS | {
            'Legenda',
            'Legenda_deuren',
            'Legenda_brandscheidingen', 'Legenda_BMI', 'Legenda_leidingen',
            '${floor}_basistekening_branddeuren_ramen',
            '${floor}_brandscheidingen', '${floor}_aantekeningen',
            '${floor}_installaties', '${floor}_installaties_behouden',
            '${floor}_installaties_nieuw',
            '${floor}_installaties_nieuw_later',
            '${floor}_installaties_adressen', '${floor}_installaties_nv_nummers',
        }),
    },
    {
        'filename': 'Brandmeldinstallatie met leidingen.pdf',
        'title': 'Brandmeldinstallatie',
        'pages': floors(SHOW_ALWAYS | DOOR_NUMBERS | {
            'Legenda',
            'Legenda_deuren',
            'Legenda_brandscheidingen', 'Legenda_BMI', 'Legenda_leidingen',
            '${floor}_basistekening_branddeuren_ramen',
            '${floor}_brandscheidingen', '${floor}_aantekeningen',
            '${floor}_installaties', '${floor}_installaties_behouden',
            '${floor}_installaties_nieuw',
            '${floor}_installaties_nieuw_later',
            '${floor}_installaties_adressen', '${floor}_installaties_nv_nummers',
            '${floor}_leidingen', '${floor}_leidingen_behouden',
            '${floor}_leidingen_nieuw', '${floor}_leidingen_nieuw_later',
        }),
    },
]

OUTPUTS['Elektra'] = [
    {
        'filename': 'Elektra.pdf',
        'title': 'Elektra',
        'pages': floors(SHOW_ALWAYS - SURFACES | DOOR_NUMBERS | {
            'Legenda',
            'Legenda_elektra',
            '${floor}_basistekening_closeup',
            '${floor}_basistekening_closeup_ruimtenummers',
            '${floor}_Elektra',
        } | replace('dist', DIST_BOXES, {
            '${floor}_Elektra_${dist}',
            '${floor}_Elektra_${dist}_WCD_etc',
            '${floor}_Elektra_${dist}_Verlichting',
            '${floor}_Elektra_${dist}_NV',
            '${floor}_Elektra_${dist}_Lasdozen',
            '${floor}_Elektra_${dist}_Installaties',
        })),
        'transform_layers': (
            {
                'layers': replace('floor', FLOORS, {'${floor}_basistekening'}),
                'opacity': 0.5,
            },
        ),
    },
    {
        # TODO: Generalize
        'filename': 'Groepenkast L02.pdf',
        'title': 'Groepenkast L02',
        'pages': [
            {
                'subtitle': 'V0 (begane grond)',
                'layers':
                    # TODO: This hides other kasten, but if different
                    # kasten are mixed within the same room, they should
                    # definitely not be hidden (maybe shown in grey, or
                    # even highlighted).
                    replace('floor', ('V0',), replace('kast', ('L02',), SHOW_ALWAYS - SURFACES | {
                        '${floor}_Elektra',
                        '${floor}_Elektra_${kast}',
                        '${floor}_Elektra_${kast}_WCD_etc',
                        '${floor}_Elektra_${kast}_Verlichting',
                        '${floor}_Elektra_${kast}_NV',
                    })),
            },
        ],
        'transform_layers': (
            {
                'layers': ('V0', 'V1', 'V2', 'V3', 'V-1', 'Gebouwdelen'),
                'scale': 0.010 / 0.006,  # Convert to 1:100 @ A3
                'scale_center': BORDER_TOP_RIGHT,
                # Clip scaled layers to the page border, to prevent
                # "sticking out" when scaling up. This wraps in another
                # layer, so the clip is applied *after* scaling, not
                # before.
                'clip': 'clip-page-border-and-title',
            },
            {
                'layers': ('Paginarand_schaal',),
                'scale': 0.010 / 0.006,  # Convert to 1:100 @ A3
                'scale_center': RULER_CENTER,
            },
            {
                'layers': replace('floor', FLOORS, {'${floor}_basistekening'}),
                'opacity': 0.5,
            }
        ),
        'texts': {
            'title-block-scale': "1:100",
            'title-block-altscale': "1:200",
        },
    },
    {
        # TODO: Generalize
        'filename': 'Groepenkast L01.pdf',
        'title': 'Groepenkast L01',
        'pages': [
            {
                'subtitle': 'V0 (begane grond)',
                'layers':
                    # TODO: This hides other kasten, but if different
                    # kasten are mixed within the same room, they should
                    # definitely not be hidden (maybe shown in grey, or
                    # even highlighted).
                    replace('floor', ('V0',), replace('kast', ('L01',), SHOW_ALWAYS - SURFACES | {
                        '${floor}_Elektra',
                        '${floor}_Elektra_${kast}',
                        '${floor}_Elektra_${kast}_WCD_etc',
                        '${floor}_Elektra_${kast}_Verlichting',
                        '${floor}_Elektra_${kast}_NV',
                    })),
            },
        ],
        'transform_layers': (
            {
                'layers': ('V0', 'V1', 'V2', 'V3', 'V-1', 'Gebouwdelen'),
                'scale': 0.008 / 0.006,  # Convert to 1:125 @ A3
                'scale_center': BORDER_TOP_LEFT,
                # Clip scaled layers to the page border, to prevent
                # "sticking out" when scaling up. This wraps in another
                # layer, so the clip is applied *after* scaling, not
                # before.
                'clip': 'clip-page-border-and-title',
            },
            {
                'layers': ('Paginarand_schaal',),
                'scale': 0.008 / 0.006,  # Convert to 1:125 @ A3
                'scale_center': RULER_CENTER,
            },
            {
                'layers': replace('floor', FLOORS, {'${floor}_basistekening'}),
                'opacity': 0.5,
            }
        ),
        'texts': {
            'title-block-scale': "1:100",
            'title-block-altscale': "1:200",
        },
    },
]

# ./export_layers.py HBW_BMI_plan.svg


# Add a Mask object, which seems to be missing from inkex. It's just a simple
# container like ClipPath
class Mask(inkex.elements._groups.GroupBase):
    """A path used to mask objects"""
    tag_name = 'mask'


class LayerSetExport(inkex.Effect):
    def __init__(self):
        inkex.Effect.__init__(self)
        self.arg_parser.add_argument("--set", action="store", dest="output_set", choices=OUTPUTS.keys(),
                                     help="Select set of output files (default is autodetect based on input filename)")
        self.arg_parser.add_argument("--path", action="store", dest="path", default="export", help="")
        self.arg_parser.add_argument("--dpi", action="store", type=int, dest="dpi", default=90)
        self.arg_parser.add_argument("--only", action="store", type=str, dest="only", default="",
                                     help="Only generate files whose filename contains the given string")
        self.arg_parser.add_argument("--keep-svgs", action="store_true",
                                     help="Keep SVGs generated for each page")

        # Hide default inkscape options that we do not need
        for action in self.arg_parser._actions:
            if action.dest in ['selected_nodes']:
                action.help = argparse.SUPPRESS

    def select_output_set(self, path):
        filename = os.path.basename(path)
        for (name, outputs) in OUTPUTS.items():
            if name in filename:
                return outputs
        return None

    def effect(self):
        output_path = os.path.expanduser(self.options.path)

        if self.options.output_set:
            outputs = OUTPUTS[self.options.output_set]
        else:
            outputs = self.select_output_set(self.options.input_file)

        if self.options.keep_svgs:
            svgdir = os.path.join(output_path, 'svg')
            os.makedirs(svgdir, exist_ok=True)

        for output in outputs:
            if self.options.only and self.options.only not in output['filename']:
                continue
            with tempfile.TemporaryDirectory() as tempdir:
                filename = "{} {}".format(datetime.date.today().isoformat(), output['filename'])
                path = os.path.join(output_path, filename)
                temp_svg = os.path.join(tempdir, 'page.svg')
                temp_pdfs = []
                print("Exporting {}".format(path))
                for (i, page) in enumerate(output['pages']):
                    print("  Page {}".format(i + 1))

                    if self.options.keep_svgs:
                        temp_svg = os.path.join(svgdir, '{}_page{}.svg'.format(filename, i + 1))

                    texts = output.pop('texts', {})
                    texts.update({
                        'title-block-title': output.get('title', ''),
                        'title-block-subtitle': page.get('subtitle', ''),
                        'title-block-date': datetime.date.today().isoformat(),
                        'title-block-sheet': '{} / {}'.format(i + 1, len(output['pages'])),
                    })

                    self.export_layers(temp_svg, page['layers'], texts, **output)
                    temp_pdf = os.path.join(tempdir, 'page{}.pdf'.format(i + 1))
                    temp_pdfs.append(temp_pdf)

                    self.export_to_pdf(temp_svg, temp_pdf)

                os.makedirs(os.path.dirname(path), exist_ok=True)
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
                'scale_center': spec.get('scale_center', BORDER_TOP_LEFT),
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
        command = "inkscape %s -d %s -o \"%s\" \"%s\"" % (area_param, self.options.dpi, output_path, svg_path)

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
