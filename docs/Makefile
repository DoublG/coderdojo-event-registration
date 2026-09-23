# Minimal makefile for Sphinx documentation

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Builds all three languages into build/html/, build/html/fr/, build/html/nl/
# — see README.md for the full extract/update/translate workflow this sits
# on top of. html_title is passed explicitly per language: a `-D language=`
# override doesn't retroactively affect conf.py's own already-executed
# `html_title = "..."` line (see the comment there).
html-all:
	$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS) $(O)
	$(SPHINXBUILD) -b html -D language=fr -D html_title="CoderDojo Belgique — Centre d'aide" "$(SOURCEDIR)" "$(BUILDDIR)/html/fr" $(SPHINXOPTS) $(O)
	$(SPHINXBUILD) -b html -D language=nl -D html_title="CoderDojo België — Helpcentrum" "$(SOURCEDIR)" "$(BUILDDIR)/html/nl" $(SPHINXOPTS) $(O)

.PHONY: help html-all Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
