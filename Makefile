.ONESHELL:

.PHONY: all
all: package

.PHONY: clean
clean:
	@rm -rf build || :
	@rm -rf dist || :
	@rm -rf openbank_testkit.egg-info || :

.PHONY: package
package:
	@python3 setup.py sdist bdist_wheel
	@python3 -m twine check dist/*

.PHONY: publish
publish:
	@python3 -m twine upload dist/*
