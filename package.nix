{ lib
, pkgs
}:
with pkgs;

python3.pkgs.buildPythonApplication {
  pname = "mindwm-manager";
  version = "0.9.1";

  src = ./.;

  propagatedBuildInputs = with python3.pkgs; [
    nats-py
    python-decouple
    aiofiles
    dbus-next
    pyte
    textfsm tabulate
  ];

  format = "pyproject";
  nativeBuildInputs = with python3.pkgs; [ setuptools ];
}
