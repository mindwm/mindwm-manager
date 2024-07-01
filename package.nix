{ lib
, pkgs
, buildPythonApplication
}:
with pkgs;

buildPythonApplication {
  pname = "mindwm-manager";
  version = "0.9.1";

  src = ./;

  format = "pyproject";
}
