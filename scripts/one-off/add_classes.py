#!/usr/bin/env python3

import sys
import re

sys.path.append('/usr/share/inkscape/extensions')
import inkex

label_attr = '{http://www.inkscape.org/namespaces/inkscape}label'

# This is a manual one-off helper script to identify different types of
# text based on the fill swatch they use, and then assigns a class to
# them to make it easier to do styling and scripting on them later.


class Effect(inkex.Effect):
    def effect(self):
        for t in self.svg.xpath('//svg:text'):
            m = re.match(r'^url\(#(.*)\)', t.style['fill'])
            if m:
                gradient = self.svg.getElement('//svg:linearGradient[@id="{}"]'.format(m.group(1)))
                try:
                    swatch = gradient.attrib['{http://www.w3.org/1999/xlink}href']

                    if swatch == '#Elektra_groep_no':
                        t.attrib['class'] = 'elektra-groep'
                        # While we're here, do a quick text replacement
                        # as well.
                        for span in t.xpath('svg:tspan'):
                            span.text = re.sub(r'L.*\.', '', span.text)
                    if swatch == '#Elektra_schakelaar_groep':
                        t.attrib['class'] = 'elektra-schakelaar'
                    if swatch == '#Elektra_armatuur':
                        t.attrib['class'] = 'elektra-armatuur'
                except KeyError:
                    print("Ignoring " + t.get_text())

        self.document.write('output.svg')


def _main():
    e = Effect()
    e.run()
    exit()


if __name__ == "__main__":
    _main()
