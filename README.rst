Copr Builder
============

A simple program for building RPM packages from Git repositories in `Copr <https://copr.fedorainfracloud.org/>`_.

Usage
-----

::

  usage: copr-builder [-h] [-v] [-p [PROJECTS ...]] [-c CONFIG] [-C COPR_CONFIG]

  Copr builder

  optional arguments:
    -h, --help            show this help message and exit
    -v, --verbose         print debug messages
    -p [PROJECTS ...], --projects [PROJECTS ...]
                          projects to build; if not given, all projects from config will be built
    -c CONFIG, --config CONFIG
                          config file location
    -C COPR_CONFIG, --copr-config COPR_CONFIG
                          Copr config file location (defaults to "~/.config/copr")


Config file structure
---------------------

::

  [project_name]
  copr_user = username
  copr_repo = reponame
  package = mypackage
  git_url = https://github.com/<user>/mypackage
  pre_archive_cmd = ./autogen.sh && ./configure
  archive_cmd = make local
  git_branch = 1.1-devel
  git_merge_branch = 1.1-release

  [another_project_name]
  copr_user =
  ...


- **project_name** -- some unique name for project/package
- **copr_user** -- FAS username or groupname
- **copr_repo** -- name of the Copr repository (without the username!)
- **package** -- name of the package that will be built

  - a *spec* file must be in the repo

- **pre_archive_cmd** -- *(optional)* command which will be run before the spec file is read. This can be used to generate or download the spec file.
- **archive_cmd** -- command for creating an archive from the source (e.g. "make local" or "git archive HEAD --prefix=package/ -o package.tar.gz")

  - this command must create at least one archive (*.tar.[gz|bz|bz2|xz]*) in the current directory

- **git_url** -- URL of the Git repo (will be used for "git clone")
- **git_branch** -- branch to use from the Git repo (e.g. "master")
- **git_merge_branch** -- optional; if you need to merge another branch into *git_branch* before running the *archive_cmd*

Copr builder will generate an SRPM from the provided git repository and send it to the specified Copr project to do a new build.
A new build will be created only if there are some changes in the repository since the last build of the package.
Release number in the SPEC file will be bumped for each build, date and git hash of the last commit are included in the release.
