import logging
from hab.site import Site
from pprint import pprint

logging.basicConfig()
logging.getLogger('hab.parsers.site').setLevel(logging.DEBUG)

sites = [
    r'\\source\source\dev\mikeh\hab_mockup\studio.json',
    r'\\source\source\dev\mikeh\hab_mockup_dev\net_dev.json',
    # r'C:\blur\dev\hab\site.json',
]

s = Site(sites)
# print(s.get('config_paths'))
# print(s.get('distro_paths'))

pprint(s)
# print(sorted(Site._reserved_keys))


# kwargs = dict(relative_root=filename.parent)
