# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information


from sphinx_pyproject import SphinxConfig

config = SphinxConfig("../pyproject.toml", globalns=globals())
project = "Kaithem Automation"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autodoc", "autoapi.extension"]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "alabaster"
html_static_path = ["_static"]

autoapi_dirs = ["../kaithem"]
autoapi_ignore = ["**/data"]


def skip_util_classes(app, what, name, obj, skip, options):
    if name.startswith("_") and not name.startswith("__"):
        skip = True
    if "._" in name and ".__" not in name:
        skip = True
    return skip


def setup(sphinx):
    sphinx.connect("autoapi-skip-member", skip_util_classes)
