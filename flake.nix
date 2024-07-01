{
  description = "A MindWM-Manager service implemented in Python";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/24.05";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = inputs@{ flake-parts, nixpkgs, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [];
      systems = [ "x86_64-linux" "aarch64-linux" ];
      perSystem = { config, self', inputs', pkgs, system, ... }:
      let
        project = pkgs.callPackage ./package.nix { };
      in { 
        packages.default = project;
        devShells.default = pkgs.mkShell {
          packages = [ project ];
          buildInputs = with pkgs; [
            natscli
          ];
        };
      };
      flake = {
      };
    };
}
