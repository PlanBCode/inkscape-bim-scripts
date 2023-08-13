#!/usr/bin/env python3

# Copyright (c) 2022 Matthijs Kooijman
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

# This script extracts info about electrical circuits and outlets from
# the floorplan SVG, performs sanity checks (writing output to a new
# SVG) and exports a tables of circuits for each breaker box (writing to
# CSV files).

import argparse
import beautifultable
import functools
import itertools
import lxml
import logging
import natsort
import pathlib
import re
import sys
import types
import typing
import matplotlib.path

from collections import defaultdict

sys.path.append('/usr/share/inkscape/extensions')
import inkex

# Apply cachingto getElementById, since we need to resolve *all* clones
# in the document to their originals (to get their bounding boxes to
# figure out the space the clone is in), which becomes really slow
# Note that this could break if we would modify the document in a way
# that should invalidate the cache, but that does not happen in this
# script.
inkex.SvgDocumentElement.getElementById = functools.cache(inkex.SvgDocumentElement.getElementById)


# Idea: Symbol superclass with Fixture, EmergencyFixture, WCD, etc. subclasses. Subclasses
# define class attributes category and label with fixed values, and a
# list of required and optional fields that the superclass (or the main
# code) can then use to check for missing or extra fields.
class Symbol(types.SimpleNamespace):
    pass


class Outlet(Symbol):
    sublayers = ['WCD_etc']
    pass


class Fixture(Symbol):
    sublayers = ['Verlichting']
    pass


class EmergencyFixture(Symbol):
    sublayers = ['NV']
    pass


class JunctionBox(Symbol):
    sublayers = ['Lasdozen']
    pass


class FixtureConnection(JunctionBox):
    # Sometimes these are combined with an outlet, so allow them in the
    # outlet layer too (ideally only when combined with an outlet, but
    # that's hard to check...)
    sublayers = ['Lasdozen', 'WCD_etc']
    pass


class Connection(Symbol):
    sublayers = ['WCD_etc']
    pass


class Switch(Symbol):
    sublayers = ['WCD_etc']
    pass


class DistributionCabinet(Symbol):
    # Allow None for the root cabinet
    sublayers = [None, 'Installaties']
    pass


class Device(Symbol):
    sublayers = ['Installaties']
    pass


class FixtureInfo(typing.NamedTuple):
    kind: str
    model: str
    count: int
    power: int


FIXTURES = {
    #'A': FixtureInfo('TL', 'Philips TBS300', 2, 58),
    'A1': FixtureInfo('TL', 'Philips TBS300', 2, 58),
    #'G': FixtureInfo('TL', 'Philips Pacific 196S', 2, 58),
    'A2': FixtureInfo('TL', 'Philips Pacific 196S', 2, 58),
    #'B': FixtureInfo('TL', 'Philips TBS300', 2, 36),
    'B1': FixtureInfo('TL', 'Philips TBS300', 2, 36),
    #'C': FixtureInfo('TL', 'Philips TMX 100/WE', 2, 36),
    'B2': FixtureInfo('TL', 'Philips TMX 100/WE', 2, 36),
    # C wordt 1x58
    #'D': FixtureInfo('TL', 'Philips TCS 221', 1, 36),
    'D1': FixtureInfo('TL', 'Philips TCS 221', 1, 36),
    #'H': FixtureInfo('TL', 'Norton AXP 1/36W IND', 1, 36),
    'D2': FixtureInfo('TL', 'Norton AXP 1/36W IND', 1, 36),
    #'E': FixtureInfo('TL', 'Proli FLF T8', 4, 18),
    'E1': FixtureInfo('TL', 'Proli FLF T8', 4, 18),
    #'F': FixtureInfo('TL', 'Norton RTP-X 4/14W HF FL83 GST T5', 4, 14),
    'F1': FixtureInfo('TL', 'Norton RTP-X 4/14W HF FL83 GST T5', 4, 14),
    'I': FixtureInfo('Plafondlamp opbouw', 'Luminance Giotto super', 2, 18),
    'J': FixtureInfo('?', 'Luminance 7063', 1, 26),
    'M': FixtureInfo('Spotje inbouw', 'Girofix 5086 GU5.3 MR16 12V', 1, 50),
    'N': FixtureInfo('Spotje inbouw', 'Ikea LED 12V', 1, 0),
    'L': FixtureInfo('?', 'Norton ARS258', 2, 58),
    'P': FixtureInfo('Spotje inbouw', 'Diep klein spotje met glas', 1, 0),
    'Q': FixtureInfo('Wandlamp buiten', 'Philips FGC111 PL-S/2P', 1, 11),
    'R': FixtureInfo('Wandspotjes', 'SLV Astina 151901/07 GU10', 2, 50),
    'S': FixtureInfo('Plafondlamp inbouw vierkant', 'Niquelight DLK 230 PL-C', 2, 18),
    'T': FixtureInfo('Plafondlamp inbouw rond', 'Ronde lampen met glasplaat en drie schroefjes', 1, 0),
    'U': FixtureInfo('Plafondlamp inbouw', 'Teknilux 62320 HF', 2, 26),
    'V': FixtureInfo('Plafondlamp buiten', 'Depa Protect 001', 2, 9),
    'Y': FixtureInfo('TL', 'Overig/onbekend', 1, 36),
    'Z': FixtureInfo(None, 'Overig/onbekend', 1, 0),
}

CIRCUITS_PER_DIST = {
    'HKL': ['K1', 'K2', 'K3', 'K4', 'K5', 'K6', 'K7', '8', '9', '10'],
    'L001': ['K1', 'K2', 'K3'],
    'L002': [i + 1 for i in range(8)] + [(i, 'Reserve') for i in [3, 4, 5, 7]],
    'L01': [i + 1 for i in range(19)] + [(i, 'Reserve') for i in [16, 17]] + [('19', 'Verlichtingsrelais')],
    'L11': [i + 1 for i in range(15)],
    'L21': [i + 1 for i in range(12)] + [(i, 'Reserve') for i in [12]],
    'L02': [i + 1 for i in range(24)] + [(i, 'Reserve') for i in [7, 10]],
    'L12': [i + 1 for i in range(9)] + [(9, 'Reserve'), 'K10', 'K11'],
    'L011': [i + 1 for i in range(5)] + [(i, 'Reserve') for i in [4, 5]],
    'NV': ['1', '2', '3'],
    'RK1': ['5F1']
}

LOCAL_SWITCHES = {'a', 'b', 'c', 'd'}


SYMBOLS = {
    'noodverlichting': {
        'class': EmergencyFixture,
        'symbol': 'NV',
    },
    'wcd-3fase': {
        # TODO: How to handle these? For now, they just have a label
        # Perilex/CEEform in the drawing
        'class': Device,
        'symbol': 'Krachtstroom',
    },
    'lamp-tl-bak': {
        'class': Fixture,
        'symbol': 'TL-bak',
    },
    'lamp-tl-balk': {
        'class': Fixture,
        'symbol': 'TL-balk',
    },
    'lamp-tl-balkje': {
        'class': Fixture,
        'symbol': 'TL-balkje',
    },
    'lamp-algemeen': {
        'class': Fixture,
        'symbol': 'Lamp',
    },
    'lamp-klein': {
        'class': Fixture,
        'symbol': 'Lampje',
    },
    'lamp-wand': {
        'class': Fixture,
        'symbol': 'Wandlamp',
    },
    'aansluitpunt': {
        'class': Connection,
        'symbol': 'Aansluitpunt',
    },
    'aansluitpunt-3fase': {
        'class': Connection,
        'symbol': 'Aansluitpunt 3-fase',
    },
    'lasdoos-licht': {
        'class': FixtureConnection,
        'symbol': 'Lichtpunt',
    },
    'lasdoos': {
        # TODO: Class
        'class': FixtureConnection,
        'symbol': 'Centraaldoos',
    },
    'blindplaat': {
        # TODO: Class
        'class': FixtureConnection,
        'symbol': 'Blindplaat',
    },
    'schakelaar-wissel': {
        'class': Switch,
        'symbol': 'Hotelschakelaar',
        'pair': True,
    },
    'schakelaar': {
        'class': Switch,
        'symbol': 'Schakelaar',
    },
    'schakelaar-4polig': {
        'class': Switch,
        'symbol': 'Vierfaseschakelaar',
    },
    'wcd-1': {
        'class': Outlet,
        'symbol': 'WCD enkel',
        'sockets': 1,
    },
    'wcd-2v': {
        'class': Outlet,
        'symbol': 'WCD dubbel vert',
        'sockets': 2,
    },
    'wcd-2h': {
        'class': Outlet,
        'symbol': 'WCD dubbel horiz',
        'sockets': 2,
    },
    'wcd-4': {
        'class': Outlet,
        'symbol': 'WCD viervoudig',
        'sockets': 4,
    },
    'wcd-plafond-1': {
        'class': Outlet,
        'symbol': 'WCD op/boven plafond enkel',
        'sockets': 1,
    },
    'wcd-plafond-2v': {
        'class': Outlet,
        'symbol': 'WCD op/boven plafond dubbel vert',
        'sockets': 2,
    },
    'wcd-plafond-2h': {
        'class': Outlet,
        'symbol': 'WCD op/boven plafond dubbel horiz',
        'sockets': 2,
    },
    'kast': {
        'class': DistributionCabinet,
        'symbol': 'Groepenkast',
    },
    'airco-plafond': {
        'class': Device,
        'symbol': 'Airco',
        'label': 'Airco',
    },
    'airco-muur': {
        'class': Device,
        'symbol': 'Airco',
        'label': 'Airco',
    },
}


def layers(doc, label_re=re.compile(".*")):
    """

    Return all layers in the given document, optionally matching their label against a given regex.

    Returns a tuple containing the layer, its full label and any groups captured by the regex.
    """
    for layer in doc.xpath('//svg:g[@inkscape:groupmode="layer"]', namespaces=inkex.NSS):
        label_attr = '{http://www.inkscape.org/namespaces/inkscape}label'
        label = layer.attrib[label_attr]
        m = re.match(label_re, label)
        if m:
            yield (layer, label) + m.groups()


def layer_for_obj(obj):
    for parent in obj.ancestors():
        if isinstance(parent, inkex.Layer):
            return parent
    return None


class ErrorCollector:
    outer_rect_style = 'stroke:#ff0000;stroke-width:3;fill:none'
    inner_rect_style = 'stroke:#ff0000;stroke-width:3;stroke-dasharray:6,3;fill:none'
    warning_text_style = 'font-size:17px;font-family:Tecnico;font-weight: bold;fill:#ff0000'
    text_box_margin = 5
    line_height = 17

    def __init__(self, logger=None):
        self.logger = logger
        self.warnings = defaultdict(lambda: defaultdict(lambda: []))

    def warn(self, obj, msg, *args, sym_attrs=None):
        if isinstance(obj, Symbol):
            sym_attrs = obj.__dict__
            obj = obj.obj

        child = obj
        top_obj = None
        top_layer = None
        layer = None
        for parent in child.ancestors():
            # Found first layer
            if layer is None and isinstance(parent, inkex.Layer):
                top_obj = child
                layer = parent

            # found root svg element
            if parent.getparent() is None:
                top_layer = child

            child = parent

        self.warnings[top_layer][(layer, top_obj)].append((obj, msg.format(*args)))

        if self.logger:
            space = sym_attrs.get('space', None) if sym_attrs else None
            if space:
                where = "{} ({})".format(layer.label, space)
            else:
                where = layer.label

            self.logger.warning(("{}: {} -> {}: " + msg).format(where, top_obj.get_id(), obj.get_id(), *args))

            if isinstance(obj, inkex.elements.TextElement):
                extra = "Text: " + obj.get_text()
            elif isinstance(obj, inkex.elements.Use):
                extra = "Clone of: " + obj.get('xlink:href')
            else:
                extra = lxml.etree.tostring(obj)
            self.logger.warning(extra)

    def bb_to_rect(self, bb, **attrs):
        return inkex.Rectangle.new(
            left=str(bb.left), top=str(bb.top),
            width=str(bb.width), height=str(bb.height),
            **attrs
        )

    def output_to_document(self):
        output = False
        for top_layer, per_top_layer in self.warnings.items():
            output_layer = inkex.Layer("{}_Warnings".format(top_layer.label))
            top_layer.append(output_layer)
            for (layer, top_obj), warnings in per_top_layer.items():
                top_bb = top_obj.bounding_box(top_obj.getparent().composed_transform())
                boxes_with_texts = [(top_bb, self.outer_rect_style, layer.label)]

                if not top_bb:
                    self.logger.warning("{}: {} -> {}: No bounding box, cannot mark warning in output document".format(
                        layer.label, top_obj.get_id(), top_obj.get_id()
                    ))
                    continue

                for obj, msg in warnings:
                    if isinstance(obj, inkex.TextElement):
                        # inkex cannot calculate a proper bounding box for
                        # text, but has shape_box() that gives a
                        # (potentially zero-size) box around all anchor
                        # points.
                        shape = obj.shape_box(obj.getparent().composed_transform())
                        m = self.text_box_margin
                        obj_bb = inkex.BoundingBox(
                            x=(shape.x.minimum - m, shape.x.maximum + m),
                            y=(shape.y.minimum - m, shape.y.maximum + m),
                        )
                        # Stretch top_bb to include this new fake bb
                        top_bb += obj_bb
                    else:
                        obj_bb = obj.bounding_box(obj.getparent().composed_transform())

                    boxes_with_texts.append((obj_bb, self.inner_rect_style, "  {}: {}".format(obj.get_id(), msg)))

                x = top_bb.left
                y = top_bb.bottom
                group = inkex.Group()
                for box, style, text in boxes_with_texts:
                    y += self.line_height
                    group.append(inkex.Group(
                        inkex.TextElement(text, x=str(x), y=str(y), style=self.warning_text_style),
                        self.bb_to_rect(box, style=style),
                    ))
                output_layer.append(group)
                output = True

        return output


class ContourTracker:
    Contour = types.SimpleNamespace

    def __init__(self, errors):
        self.errors = errors
        self.contours = defaultdict(lambda: [])

    def find_spaces(self, doc):
        contour_re = re.compile(r'([^_]*).*_ruimtecontouren')
        for (layer, label, floor) in layers(doc, contour_re):
            self.process_contour_layer(layer, floor)

        number_re = re.compile(r'([^_]*).*_(?:ruimtenummers|buitenlabels)')
        for (layer, label, floor) in layers(doc, number_re):
            self.process_number_layer(layer, floor)

    def add_contour(self, floor, obj, **kwargs):
        path_string = None
        if isinstance(obj, inkex.elements.PathElement):
            path_string = obj.attrib['d']
        elif isinstance(obj, inkex.elements.Rectangle):
            path_string = obj.get_path()
        else:
            self.errors.warn(obj, "Unknown contour object")
            return

        path = inkex.paths.Path(path_string)
        transform = obj.composed_transform()
        if transform:
            path.transform(transform, inplace=True)

        polygon = matplotlib.path.Path([(p.x, p.y) for p in path.control_points])

        self.contours[floor].append(self.Contour(polygon=polygon, obj=obj, **kwargs))

    def find_contour(self, floor, obj):
        bbox = obj.bounding_box(obj.getparent().composed_transform())
        if bbox is None:
            self.errors.warn(obj, "Object without bounding box?")
            return None
        center = bbox.center
        for contour in self.contours[floor]:
            if contour.polygon.contains_points([(center.x, center.y)]):
                return contour
        return None


class SpaceNumbers(ContourTracker):
    def __init__(self, errors, doc):
        super().__init__(errors)
        self.find_spaces(doc)

    def find_spaces(self, doc):
        contour_re = re.compile(r'([^_]*).*_ruimtecontouren')
        for (layer, label, floor) in layers(doc, contour_re):
            self.process_contour_layer(layer, floor)

        number_re = re.compile(r'([^_]*).*_(?:ruimtenummers|buitenlabels)')
        for (layer, label, floor) in layers(doc, number_re):
            self.process_number_layer(layer, floor)

        for contour in itertools.chain(*self.contours.values()):
            if not hasattr(contour, 'number'):
                self.errors.warn(contour.obj, 'Contour without number')
                contour.number = None

    def process_contour_layer(self, layer, floor):
        for obj in layer:
            self.add_contour(floor, obj)

    def process_number_layer(self, layer, floor):
        for obj in layer:
            if isinstance(obj, inkex.elements.TextElement):
                number = obj.get_text(sep=" ")
                contour = self.find_contour(floor, obj)
                if contour:
                    if hasattr(contour, 'number') and contour.number != number:
                        self.errors.warn(obj, "Duplicate space number ({} and {})".format(contour.number, number))
                    else:
                        contour.number = number
            else:
                self.errors.warn(obj, "Unknown object in space number layer")

    def find_space(self, floor, obj):
        contour = self.find_contour(floor, obj)
        if contour:
            return contour.number
        return None


class ProcessElektra(inkex.EffectExtension):
    def __init__(self):
        super().__init__()
        self.symbols = []
        self.errors = ErrorCollector(logger=logging)

        self.arg_parser.add_argument("--mark-questions", action="store_true",
                                     help="Mark questionmarks in the output SVG")

        self.arg_parser.add_argument("--write-tables", type=str,
                                     help="Write CSV tables to the given directory")

        # Hide default inkscape options that we do not need
        for action in self.arg_parser._actions:
            if action.dest in ['selected_nodes']:
                action.help = argparse.SUPPRESS

    def effect(self):
        doc = self.document
        self.space_numbers = SpaceNumbers(self.errors, doc)
        self.dist_contours = ContourTracker(self.errors)

        label_re = re.compile(r'(.*)_Elektra_([^_]*)(?:_(.*))?')
        for (layer, label, floor, dist, sublayer) in layers(doc, label_re):
            if sublayer == 'Leidingen':
                continue
            self.process_layer(layer, floor=floor, dist=dist, sublayer=sublayer)

        circuits = list(self.circuit_tables())

        # print(self.component_table())
        print(self.switches_table())
        for dist, table in circuits:
            print()
            print(repr(dist))
            print(table)

        if self.options.write_tables:
            for dist, table in circuits:
                dirname = pathlib.Path(self.options.write_tables) / 'circuits'
                dirname.mkdir(parents=True, exist_ok=True)
                fname = dirname / f'{dist}.csv'
                table.to_csv(str(fname))

    def has_changed(self, ret):
        # String means filename specified, default is sys.stdout
        # This only writes output when an explicit filename is specified
        # and there were errors/warnings to write.
        if isinstance(self.options.output, str):
            if self.errors.output_to_document():
                print("Writing warnings to {}".format(self.options.output))
                return True
            else:
                print("No warnings, not writing output file")

        return False

    def component_table(self):
        counts = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: 0)))
        for symbol in self.symbols:
            if hasattr(symbol, 'circuit'):
                counts[symbol.dist][symbol.circuit][symbol.symbol] += 1

        table = beautifultable.BeautifulTable()
        table.set_style(beautifultable.BeautifulTable.STYLE_DOTTED)
        table.columns.header = ["Kast", "Groep", "Symbool", "Aantal"]
        table.columns.alignment["Symbool"] = beautifultable.BeautifulTable.ALIGN_RIGHT
        for dist, percircuit in counts.items():
            for circuit, persymbol in percircuit.items():
                for symbol, count in persymbol.items():
                    table.rows.append([dist, circuit, symbol, count])
                    dist = ""
                    circuit = ""

        return table

    def group_by(self, it, attr, default=None):
        def key(v):
            return getattr(v, attr, default)
        # Filter out things without that attribute by default (since
        # comparing strings with None in sorted is impossible), but
        # still allow e.g. the empty string (or some other comparable
        # value) to return those values anyway.
        if default is None:
            it = (v for v in it if hasattr(v, attr))
        return itertools.groupby(sorted(it, key=key), key=key)

    def circuit_tables(self):

        for (dist, per_dist) in self.group_by(self.symbols, 'dist'):
            table = beautifultable.BeautifulTable()
            table.set_style(beautifultable.BeautifulTable.STYLE_DEFAULT)
            table.columns.header = ["Groep", "Omschrijving"]
            table.columns.alignment["Omschrijving"] = beautifultable.BeautifulTable.ALIGN_LEFT

            circuits = defaultdict(lambda: [])
            # TODO: Better handle CIRCUITS_PER_DIST? Should we warn if a
            # labeled circuit also has symbols? Should we warn if
            # symbols have an unkown circuit?
            for circuit in CIRCUITS_PER_DIST.get(dist, []):
                if isinstance(circuit, tuple):
                    # Add a dummy device so the given label is shown for
                    # this circuit
                    circuit, label = circuit
                    circuits[str(circuit)].append(Device(label=label, space=''))
                else:
                    # Just put an empty circuit in the list, to make
                    # sure it shows up in the table
                    circuits[str(circuit)]

            for (circuit, symbols) in self.group_by(per_dist, 'circuit'):
                # TODO: Option?
                if circuit == "NC" or (isinstance(circuit, str) and "?" in circuit):
                    continue

                circuits[circuit].extend(symbols)

            def circuitkey(item):
                # Strip K for 3-phase groups
                return item[0].lstrip('K')

            for (circuit, symbols) in natsort.natsorted(circuits.items(), key=circuitkey):
                table.rows.append([circuit, self.symbols_description(symbols)])
            yield(dist, table)

    def symbols_description(self, symbols, show_fixture_connections=False, show_switches=False):
        sockets = defaultdict(lambda: 0)
        efixtures = defaultdict(lambda: 0)
        fixtures = defaultdict(lambda: defaultdict(lambda: 0))
        labels = defaultdict(lambda: defaultdict(lambda: 0))
        fixture_connections = defaultdict(lambda: 0)
        switches = defaultdict(lambda: 0)

        for symbol in symbols:
            label = getattr(symbol, 'label', None)
            # Ensure all spaces (including None) are strings, to
            # allow sorting to always work.
            space = str(symbol.space)
            if label:
                if label == 'AC' and isinstance(symbol, Outlet):
                    # Since all aircos are listed as devices, but not
                    # all have their outlet listed, ignore the outlets
                    # for now.
                    # TODO: Do this based on wiring
                    print(f'Ignoring Airco outlet, assuming device is listed: {symbol}')
                    continue
                labels[label][space] += 1
            elif isinstance(symbol, DistributionCabinet):
                labels[symbol.distbox_label][space] += 1
            elif isinstance(symbol, Outlet):
                if hasattr(symbol, 'switch_group'):
                    # TODO: Do this based on wiring
                    print(f'Ignoring switchable outlet, assuming connected fixture is listed: {symbol}')
                    continue
                sockets[space] += symbol.sockets
            elif isinstance(symbol, EmergencyFixture):
                efixtures[space] += 1
            elif isinstance(symbol, Fixture):
                fixtures[space][symbol.fixture.power] += symbol.fixture.count
            elif isinstance(symbol, FixtureConnection):
                fixture_connections[space] += 1
            elif isinstance(symbol, Switch):
                switches[space] += 1
            elif isinstance(symbol, Device):
                print(f'Device without label: {symbol}')
            elif isinstance(symbol, Connection):
                print(f'Connection without label: {symbol}')
            else:
                print(f'Unknown symbol for circuits list: {symbol}')

        description = []
        if switches and show_switches:
            description.append('Schakelaars: {}'.format(', '.join(
                f'{space} ({count}×)' if count > 1 else f'{space}'
                for space, count in natsort.natsorted(switches.items()))
            ))

        if fixture_connections and show_fixture_connections:
            description.append('Lichtpunten: {}'.format(', '.join(
                f'{space} ({count}×)'
                for space, count in natsort.natsorted(fixture_connections.items()))
            ))

        if sockets:
            # TODO: 3-phase separately?
            description.append('WCD\'s: {}'.format(', '.join(
                f'{space} ({count}×)'
                for space, count in natsort.natsorted(sockets.items()))
            ))
        if efixtures:
            description.append('NV: {}'.format(', '.join(
                f'{space} ({count}×)' if count > 1 else f'{space}'
                for space, count in natsort.natsorted(efixtures.items()))
            ))
        if fixtures:
            #description.append('Verlichting: {}, Totaal {}W'.format(
            description.append('Verlichting: {}'.format(
                ', '.join('{} ({})'.format(
                    space,
                    ', '.join(
                        f'{count}×{power}W' if power else f'{count}×'
                        for power, count in natsort.natsorted(powers.items())
                    )
                ) for space, powers in sorted(fixtures.items())),
                #sum(power * count for powers in fixtures.values() for power, count in powers.items())
            ))
        if labels:
            description.extend('{}: {}'.format(
                label,
                ', '.join(
                    f'{space} ({count}×)' if count > 1 else f'{space}'
                    for space, count in natsort.natsorted(spaces.items())
                )
            ) if spaces != {'': 1} else label for label, spaces in sorted(labels.items()))

        # space+ means newline in asciidoc
        return ' +\n'.join(description)

    def switches_table(self):
        table = beautifultable.BeautifulTable()
        table.set_style(beautifultable.BeautifulTable.STYLE_DEFAULT)
        table.columns.header = ["Schakelaar", "Omschrijving"]

        def switch_key(obj):
            switch_group = getattr(obj, 'switch_group', None)
            if switch_group is None:
                return None
            if switch_group in LOCAL_SWITCHES:
                return '{} ({})'.format(switch_group, obj.space)
            return switch_group

        for (group, symbols) in self.group_by(self.symbols, 'global_switch_group'):
            switches, others = [], []
            for symbol in symbols:
                if isinstance(symbol, Switch):
                    switches.append(symbol)
                else:
                    others.append(symbol)

            pairs = [getattr(s, 'pair', False) for s in switches]
            if not switches:
                self.errors.warn(others[0], "Switch group without switches: {}", group)
            elif len(switches) < 2 and pairs[0]:
                self.errors.warn(switches[0], "Only one switch in pair group: {}", group)
            elif len(switches) == 2 and pairs[0] != pairs[1]:
                self.errors.warn(switches[0], "Pair and single switches mixed in group: {}", group)
            elif len(switches) > 2 or len(switches) > 1 and not pairs[0]:
                self.errors.warn(switches[0], "Too many switches in group: {}", group)

            all_symbols = itertools.chain(switches, others)
            description = self.symbols_description(all_symbols, show_switches=True, show_fixture_connections=True)
            table.rows.append([group, description])

        return table

    def process_layer(self, layer, **kwargs):
        for obj in layer:
            if not isinstance(obj, inkex.elements.Layer):
                self.process_obj(obj, obj, **kwargs)

    def process_obj(self, top, obj, **kwargs):
        if obj.attrib.get('class', None) in ['elektra-ignore', 'elektra-notitie']:
            pass
        elif obj.attrib.get('class', None) == 'elektra-kastgebied':
            if kwargs['sublayer'] is not None:
                self.errors.warn(obj, "Dist contour should be in root layer for dist")
            self.dist_contours.add_contour(kwargs['floor'], obj, dist=kwargs['dist'])
        elif isinstance(obj, inkex.elements.Use):
            # This uses xlink:href rather than the href python
            # attribute, since the latter does a lookup for the cloned
            # object, which we usually do not need.
            href = obj.get('xlink:href').strip('#')

            # Determine the space and dist contour as late as possible,
            # but only one and always before traversing a clone or
            # processing a symbol
            if 'space' not in kwargs:
                space = self.space_numbers.find_space(kwargs['floor'], obj)
                if space is None:
                    self.errors.warn(obj, "Not inside any space", sym_attrs=kwargs)
                kwargs['space'] = space

            if 'contour_dist' not in kwargs:
                contour = self.dist_contours.find_contour(kwargs['floor'], obj)
                if contour is not None:
                    kwargs['contour_dist'] = contour.dist
                else:
                    # Explicitly set None, to prevent the cloned object
                    # position from being used
                    kwargs['contour_dist'] = None

            info = SYMBOLS.get(href, None)
            if info:
                # Found an actual symbol, process it with all the info
                # we collected
                self.process_symbol(info, top, obj, **kwargs)
            else:
                # This must be a clone of a symbol with labels and all
                original = obj.href

                clone_layer = layer_for_obj(top)
                original_layer = layer_for_obj(original)
                if clone_layer != original_layer:
                    self.errors.warn(obj, "Clone in different layer (original: {}, clone: {}",
                                     original_layer.label, clone_layer.label,
                                     sym_attrs=kwargs)
                else:
                    self.process_obj(top, original, **kwargs)

        elif isinstance(obj, inkex.elements.Group):
            later = []
            for part in obj:
                cls = part.attrib.get('class', None)
                text = None
                if isinstance(part, inkex.elements.TextElement):
                    text = part.get_text()

                class_to_attr = {
                    'elektra-groep': 'circuit',
                    'elektra-schakelaar': 'switch_group',
                    'elektra-armatuur': 'fixture_id',
                    'elektra-kast': 'distbox_label',
                    'elektra-label': 'label',
                    'elektra-ruimte': 'space',
                }

                attr = class_to_attr.get(cls, None)

                if self.options.mark_questions and text and '?' in text:
                    self.errors.warn(part, "Question")

                # TODO: Check swatch based on class?
                if text and attr:
                    if attr in kwargs:
                        self.errors.warn(
                            part, "Duplicate attribute {} ('{}' and '{}')".format(cls, kwargs[attr], text)
                        )
                    kwargs[attr] = text
                else:
                    later.append(part)

            for part in later:
                self.process_obj(top, part, **kwargs)

        else:
            text = None
            if isinstance(obj, inkex.elements.TextElement):
                text = obj.get_text()

            if text and '?' in text:
                # Ignore text with question marks, those can be
                # flagged separately with --mark-questions if needed
                pass
            elif text is not None and text == "":
                # Ignore empty texts (these are easy to create
                # accidentaly)
                pass
            else:
                # Lookup space for the error message
                if 'space' not in kwargs:
                    kwargs['space'] = self.space_numbers.find_space(kwargs['floor'], obj)
                self.errors.warn(obj, "Unknown object", sym_attrs=kwargs)

    def process_symbol(self, info, top, obj, **kwargs):
        kwargs.update(**info)
        cls = kwargs.pop('class')

        # TODO: Move to separate check function?
        if kwargs['sublayer'] not in cls.sublayers:
            self.errors.warn(obj, "Symbol in wrong layer (found: {}, expected: {})",
                             kwargs['sublayer'], cls.sublayers, sym_attrs=kwargs)

        circuit = kwargs.get('circuit', None)
        if circuit:
            # This regex ended up a bit complex, but needed to support
            # both dot-separated like L01.2 or also L01.K2, but also
            # unseparated like NV1, and I wanted to have only two
            # capture groups for dist and circuit. I'm not sure I
            # understand it exactly, but it works for all cases needed:
            #   c = ['L1.2', 'L1.23', 'L01.2', 'L01.23', 'HKL.2', 'HKL.23', 'HKL.K2',
            #       'NV1', 'NV?', '?', '2', '23', 'NC'])]
            #   [re.match(r'([A-Z]+|.*(?=\.)|)\.?((?<=\.).*|[0-9?+]+|(?<=^).*)$', s).groups() for s in c]
            m = re.match(r'([A-Z]+|.*(?=\.)|)\.?((?<=\.).*|[0-9?+]+|(?<=^).*)$', circuit)
            label_dist, new_circuit = m.groups()

            contour_dist = kwargs.get('contour_dist', None)
            layer_dist = kwargs['dist']
            if not label_dist and contour_dist != layer_dist:
                self.errors.warn(obj, "Symbol outside of its dist contour must have explicit dist in circuit"
                                      "(circuit: {}, dist: {}, contour: {})", circuit, layer_dist, contour_dist,
                                      sym_attrs=kwargs)

            if label_dist and label_dist != layer_dist:
                self.errors.warn(obj, "Distribution box in circuit does not match layer (circuit: {}, layer: {})",
                                 circuit, layer_dist, sym_attrs=kwargs)
            else:
                circuit = new_circuit
                kwargs['circuit'] = circuit

        fixture_id = kwargs.get('fixture_id', None)
        if cls == Fixture and not fixture_id:
            self.errors.warn(obj, 'Missing fixture type', sym_attrs=kwargs)
            fixture_id = 'Z'

        # TODO: Remove ? exception later
        if fixture_id == '?':
            fixture_id = 'Z'

        if fixture_id:
            try:
                kwargs['fixture'] = FIXTURES[fixture_id]
            except KeyError:
                self.errors.warn(obj, f'Unknown fixture type: {fixture_id}', sym_attrs=kwargs)

        kwargs['obj'] = obj

        # If multiple switch groups are specified (e.g. a+b), just
        # generate multiple symbols for simplicity
        for switch_group in kwargs.get('switch_group', '').split('+'):
            if switch_group:
                if switch_group in LOCAL_SWITCHES:
                    kwargs['global_switch_group'] = '{}-{}'.format(kwargs['space'], switch_group)
                else:
                    kwargs['global_switch_group'] = switch_group

            self.symbols.append(cls(**kwargs))


if __name__ == "__main__":
    ProcessElektra().run()
