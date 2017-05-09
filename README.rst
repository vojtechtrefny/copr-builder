Copr Builder
============

A simple program for building projects from Git repository in Copr.

Usage
-----

::

  usage: copr-builder.py [-h] [-v] [-p [PROJECTS [PROJECTS ...]]] [-c CONFIG]

  Copr builder

  optional arguments:
    -h, --help            show this help message and exit
    -v, --verbose         print debug messages
    -p [PROJECTS [PROJECTS ...]], --projects [PROJECTS [PROJECTS ...]]
                          projects to build; if not given, all projects from
                          config will be built
    -c CONFIG, --config CONFIG
                          config file location

Config file structure
--------------------

::

  [project_name]
  copr_user = username
  copr_repo = reponame
  package = mypackage
  git_url = https://github.com/<user>/mypackage
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

- **archive_cmd** -- command for creating archive from the source (e.g. "make local" or "git archive HEAD --prefix=package/ -o package.tar.gz")

  - this command must create a single archive (*.tar.[gz|bz|bz2|xz]*) in the current directory

- **git_url** -- URL of the Git repo (will be used for "git clone")
- **git_branch** -- branch to use from the Git repo (e.g. "master")
- **git_merge_branch** -- optional; if you need to merge another branch into *git_branch* before running the *archive_cmd*
