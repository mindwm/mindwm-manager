{ lib
, pkgs
, python
}:
with pkgs;

python3.pkgs.buildPythonApplication {
  pname = "mindwm-manager";
  version = "0.9.1";

  src = ./.;

  propagatedBuildInputs = [ python ];

  format = "pyproject";
  nativeBuildInputs = with python3.pkgs; [ setuptools ];
}
