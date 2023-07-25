{ pkgs ? import <nixpkgs> {} }:
with pkgs.python310Packages;
buildPythonApplication {
  pname = "kaithem";
  version = "0.64.3";

  propagatedBuildInputs = with pkgs; [
    gtk3 # Pango
    gobject-introspection # Pango

    gst_all_1.gstreamer
    #gst_all_1.gstreamer.dev # gst-inspect
    gst_all_1.gst-plugins-base # playbin
    (gst_all_1.gst-plugins-good.override { gtkSupport = true; }) # gtksink
    gst_all_1.gst-plugins-bad
    gst_all_1.gst-plugins-ugly
    gst_all_1.gst-libav
    mpv
    networkmanager
    jack2
    libjack2

    python310Packages.numpy
    python310Packages.python-rtmidi
    python310Packages.pillow
    python310Packages.paho-mqtt
    python310Packages.msgpack
    python310Packages.python-pam
    python310Packages.scikit-image
    python310Packages.pyserial
    python310Packages.netifaces
    python310Packages.psutil
    python310Packages.evdev
    python310Packages.setproctitle
    fluidsynth
    (
    buildPythonPackage rec {
      pname = "tflite-runtime";
      version = "2.13.0";
      format="wheel";

      src = fetchurl {
        url=if pkgs.system == "x86_64-linux"
                then "https://files.pythonhosted.org/packages/93/b3/0c6d6a58e67f9af035863b82ef09926eacc2ab43b2eb537cb345c53b4c1e/tflite_runtime-2.13.0-cp310-cp310-manylinux2014_x86_64.whl"
                else "https://files.pythonhosted.org/packages/ac/01/ac170459779f503581c492d65d1d339d223ac09a7e92f379eddc689678ec/tflite_runtime-2.13.0-cp310-cp310-manylinux2014_aarch64.whl";

        sha256 = if pkgs.system == "x86_64-linux"
                then "sha256-bmAIzUsLrKlHrwu8KxhQlvF/jm/EbH5vr/vQJvzF2K8="
                else "";
      };
      doCheck = false;
      propagatedBuildInputs = [
        # Specify dependencies
        pkgs.python310Packages.numpy
      ];
    }
  )

      (
    buildPythonPackage rec {
      pname = "JACK-Client";
      version = "0.5.4";
      format="wheel";

      src = fetchurl {
        url="https://files.pythonhosted.org/packages/17/41/de1269065ff0d1bda143cc91b245aef3165d9259e27904a4a59eab081e0b/JACK_Client-0.5.4-py3-none-any.whl";
        sha256 = "sha256-UsphZEONO3+M/azl9vqzxyJP5jAi78hccCmGLUNbznM=";
      };
      doCheck = false;
            propagatedBuildInputs = [
        # Specify dependencies
        pkgs.python310Packages.numpy
        pkgs.python310Packages.cffi
        libjack2
        jack2
      ];
    }
  )



  ];
  doCheck = false;
  src = ./.;

  #ldconfig from iconv is required to make _find_path in Python Ctypes work
  postFixup = ''
  wrapProgram $out/bin/kaithem \
    --set PATH ${lib.makeBinPath (with pkgs; [
      mpv
      networkmanager
      iconv
      coreutils
      bash
      binutils_nogold
    ])}
'';

}