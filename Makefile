pylint:
	@echo "*** Running pylint ***"
	@PYTHONPATH=. python3 tests/pylint/runpylint.py

pep8:
	@echo "*** Running pycodestyle compliance check ***"
	@python3 -m pycodestyle --ignore=E501,E402,E731,W504 copr_builder/ tests/

build:
	python3 setup.py build

check:
	@status=0; \
	$(MAKE) pylint || status=1; \
	$(MAKE) pep8 || status=1; \
	exit $$status

clean:
	-@rm -f copr_builder/*.pyc
	-@rm -rf dist copr_builder.egg-info pylint-log build
	@python3 setup.py -q clean

install:
	python3 setup.py install --root=$(DESTDIR)

.PHONY: check pep8 pylint clean install
