Name:           agymcp
Version:        @VERSION@
Release:        1%{?dist}
Summary:        Antigravity MCP Installer & Manager (PyQt6 GUI + CLI + OAuth 2.1)
License:        MIT
URL:            https://github.com/Loriek-cyber/agymcp
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.10
Requires:       python3dist(pyqt6)

%description
Antigravity MCP Installer & Manager (agymcp) is a lightweight native PyQt6
desktop app and CLI utility to install, authenticate (OAuth 2.1 + PKCE), and
manage Model Context Protocol (MCP) servers on Google Antigravity directly from
a link (e.g. https://api.streak.com/mcp).

%prep
%setup -q

%build
# Pure Python noarch package; nothing to compile.

%install
rm -rf %{buildroot}
install -d %{buildroot}%{_datadir}/%{name}
cp -r agymcp assets README.md pyproject.toml %{buildroot}%{_datadir}/%{name}/

install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/%{name} << 'EOF'
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/agymcp${PYTHONPATH:+:${PYTHONPATH}}"
exec /usr/bin/python3 -m agymcp.cli "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/%{name}

install -d %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m 0644 assets/agymcp.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/agymcp.svg
install -d %{buildroot}%{_datadir}/pixmaps
install -m 0644 assets/agymcp.svg %{buildroot}%{_datadir}/pixmaps/agymcp.svg

install -d %{buildroot}%{_datadir}/applications
sed 's|^Exec=.*|Exec=/usr/bin/agymcp|' assets/agymcp.desktop > %{buildroot}%{_datadir}/applications/agymcp.desktop
chmod 0644 %{buildroot}%{_datadir}/applications/agymcp.desktop

%post
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q %{_datadir}/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -f -t %{_datadir}/icons/hicolor || true
fi

%postun
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q %{_datadir}/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -f -t %{_datadir}/icons/hicolor || true
fi

%files
%{_bindir}/%{name}
%{_datadir}/%{name}
%{_datadir}/applications/agymcp.desktop
%{_datadir}/icons/hicolor/scalable/apps/agymcp.svg
%{_datadir}/pixmaps/agymcp.svg

%changelog
* Thu Nov 19 2026 Loriek-cyber <loriek@users.noreply.github.com> - @VERSION@-1
- Automated Fedora RPM release build with desktop menu & icon cache hooks
