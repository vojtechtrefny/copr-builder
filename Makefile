APPNAME=copr-builder
VERSION=$(shell python3 setup.py --version)

all:

pylint:
	@echo "*** Running pylint ***"
	@PYTHONPATH=. python3 tests/pylint/runpylint.py

pep8:
	@echo "*** Running pycodestyle compliance check ***"
	@python3 -m pycodestyle --ignore=E501,E402,E731,W504 copr_builder/ tests/

build:
	python3 setup.py build

tag:
	tag='$(VERSION)' ; \
	git tag -a -s -m "Tag as $$tag" -f $$tag && \
	echo "Tagged as $$tag"

release: tag archive

archive:
	@git archive --format=tar --prefix=$(APPNAME)-$(VERSION)/ $(VERSION) | tar -xf -
	@( cd $(APPNAME)-$(VERSION) && python3 setup.py -q sdist --dist-dir .. )
	@rm -rf $(APPNAME)-$(VERSION)
	@echo "The archive is in $(APPNAME)-$(VERSION).tar.gz"

local:
	@python3 setup.py -q sdist --dist-dir .
	@echo "The archive is in $(APPNAME)-$(VERSION).tar.gz"

bumpver:
	@NEWSUBVER=$$((`echo $(VERSION) | cut -d . -f 2` + 1)) ; \
	NEWVERSION=`echo $(VERSION).$$NEWSUBVER | cut -d . -f 1,3` ; \
	sed -i "s/version='$(VERSION)'/version='$$NEWVERSION'/" setup.py ; \
	sed -i "s/Version:   $(VERSION)/Version:   $$NEWVERSION/" copr-builder.spec ; \

check:
	@status=0; \
	$(MAKE) pylint || status=1; \
	$(MAKE) pep8 || status=1; \
	exit $$status

test:
	@echo "*** Running tests ***"
	@python3 -m pytest

clean:
	-@rm -f copr_builder/*.pyc
	-@rm -rf dist copr_builder.egg-info pylint-log build
	@python3 setup.py -q clean

install:
	python3 setup.py install --root=$(DESTDIR)

.PHONY: check pep8 pylint clean install
