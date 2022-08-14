%global pyname copr_builder

Name:      copr-builder
Version:   1.1
Release:   1%{?dist}
Summary:   Automation tool for building in Copr

License:   GPLv2+
Url:       https://github.com/vojtechtrefny/%{name}
Source0:   https://github.com/vojtechtrefny/%{name}/archive/%{version}/%{name}-%{version}.tar.gz

BuildArch: noarch

BuildRequires: make
BuildRequires: python3-devel
BuildRequires: python3-setuptools
BuildRequires: python3-pytest
BuildRequires: python3-copr

Requires: python3-copr
Requires: python3-packaging

%description
A simple program for building RPM packages from Git repositories in Copr.

%prep
%autosetup -n %{name}-%{version} -p1

%build
make PYTHON=%{__python3}

%install
make DESTDIR=%{buildroot} PYTHON=%{__python3} install

%check
make PYTHON=%{__python3} test

%files -n %{name}
%license LICENSE
%{python3_sitelib}/%{pyname}*egg*
%{python3_sitelib}/%{pyname}/
%{_bindir}/%{name}

%changelog
* Sat May 21 2022 Vojtech Trefny <vtrefny@redhat.com> - 1.0-1
- Initial packaging of copr-builder.
