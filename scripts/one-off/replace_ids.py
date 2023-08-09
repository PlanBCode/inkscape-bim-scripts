#!/usr/bin/env python3

import sys
import collections

sys.path.append('/usr/share/inkscape/extensions')
import inkex

label_attr = '{http://www.inkscape.org/namespaces/inkscape}label'

# This is a manual one-off helper script to replace the id of SVG
# elements with another. This updates the elements themselves, and
# clones that refer to them.
# This dict contains {old_id: new_id}
IDS = {
    'g177039': 'noodverlichting',
    'g142405': 'wcd-3fase',
    'g36446': 'lamp-tl-bak',
    'g36440': 'lamp-tl-balk',
    'g77816': 'lamp-tl-balkje',
    'g36443': 'lamp-algemeen',
    'g1463925': 'lamp-klein',
    'g250877': 'lamp-wand',
    'g263647': 'aansluitpunt',
    'g1844386': 'aansluitpunt-3fase',
    'g1334400': 'lasdoos-licht',
    'g43311': 'lasdoos',
    'g261856': 'schakelaar-wissel',
    'g260038': 'schakelaar',
    'g106414': 'schakelaar-4polig',
    'g189066': 'wcd-1',
    'g189869': 'wcd-2v',
    'g73365': 'wcd-2h',
    'g189983': 'wcd-4',
    'g731008': 'wcd-plafond-1',
    'g731016': 'wcd-plafond-2v',
    'g126007': 'wcd-plafond-2h',
    'g37190': 'kast',
    'g512411': 'airco-plafond',
    'g559770': 'airco-muur',
    'g189490': 'wcd-ongeaard-1',
    'g189879': 'wcd-ongeaard-2v',
    'g43006': 'doorvoer-omhoog',
    'g43925': 'doorvoer-omlaag',
    'g2710884': 'doorvoer-overig',
    'g587791': 'blindplaat',
}


class Effect(inkex.EffectExtension):
    def effect(self):
        clones_updated = collections.defaultdict(lambda: 0)
        for old_id, new_id in IDS.items():
            obj = self.svg.getElementById(old_id)
            if obj is not None:
                obj.set('id', new_id)
                print("{}->{}: Updated id".format(old_id, new_id))

        for clone in self.svg.xpath('//svg:use'):
            href = clone.get('xlink:href').strip('#')
            new_href = IDS.get(href, None)
            if new_href:
                clone.set('xlink:href', '#' + new_href)
                clones_updated["{}->{}".format(href, new_href)] += 1

        for ids, count in clones_updated.items():
            print("{}: Updated {} clones".format(ids, count))


if __name__ == "__main__":
    e = Effect()
    e.run()
    exit()
