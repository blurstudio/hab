This is a isolated site configuration specifically for testing omittable_distros.
This allows for custom configuration of the default config without affecting other tests.

* The [default](configs/default.json) config defines `omittable_distros` that can be
inherited by other distros. It lists two distros that do not exist for this site.
* [omittable/defined](omittable/defined.json) defines `omittable_distros` replacing it with a modified
list of distros to omit for this URI and its children.
* [omittable/inherited](omittable/inherited.json) does not define the `omittable_distros` and inherits
from its parents which aren't defined so it finally inherits the value defined
in the  `default` config.
