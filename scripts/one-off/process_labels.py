#!/usr/bin/env python3

# Based on https://github.com/hfichtenberger/inkscape-export-overlays
#
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

import copy
import datetime
import os
import subprocess
import sys
import tempfile

sys.path.append('/usr/share/inkscape/extensions')
import inkex

label_attr = '{http://www.inkscape.org/namespaces/inkscape}label'

# This is a manual one-off helper script that does some processing of
# text 
# elements with another. This updates the elements themselves, and
# clones that refer to them.
# This dict contains {old_id: new_id}

class Effect(inkex.Effect):
    def effect(self):
        # Only process text in this particular label
        for layer in self.svg.xpath('//svg:g[contains(@inkscape:label, "bestemming")]', namespaces=inkex.NSS):
            print("Layer", layer.attrib[label_attr])
            copylayerlabel = layer.attrib[label_attr].replace("bestemming", "oppervlaktes")
            copylayer = self.svg.findone('//svg:g[@inkscape:label="{}"]'.format(copylayerlabel))
            for text in layer.xpath('.//svg:text'):
                # Delete text nodes without any children
                if not any(True for _ in text):
                    print("Deleting empty text", text.attrib['id'])
                    text.delete()
                    continue

                # Flatten nested tspans
                spans = text.xpath('svg:tspan')
                if len(spans) == 1 and len(spans[0].xpath('svg:tspan')) > 0:
                    print("Flattening nested text", text.attrib['id'])
                    for subspan in spans[0].xpath('svg:tspan'):
                        text.append(subspan)
                        spans[0].delete()

                print("Text", text.attrib['id'], text.get_text())

                # Make a copy of text elements with room use labels for
                # entering room surface area.  Position it directly
                # below the original text.
                copytext = text.copy()
                copylayer.append(copytext)
                for i, span in enumerate(copytext.xpath('svg:tspan')):
                    if i == 0:
                        span.text = 'm²'
                    else:
                        span.delete()

                OFFSET = 30
                text.attrib['y'] = str(float(text.attrib['y']) + OFFSET)
                for span in text.xpath('svg:tspan'):
                    span.attrib['y'] = str(float(span.attrib['y']) + OFFSET)

        self.document.write('output.svg')

def _main():
    e = Effect()
    e.run()
    exit()


if __name__ == "__main__":
    _main()
