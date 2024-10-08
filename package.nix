{ lib
, pkgs
, tmuxp
, python
}:
with pkgs;

python3.pkgs.buildPythonApplication {
  pname = "mindwm-manager";
  version = "0.9.1";

  src = ./.;

  propagatedBuildInputs = [ python dbus ];

  format = "pyproject";
  nativeBuildInputs = with python3.pkgs; [ setuptools ];
}
