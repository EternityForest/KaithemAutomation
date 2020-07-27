# These are templates for effect data. Note that they contain everything needed to generate and interface for
# And use a gstreamer element. Except fader, which is special cased.
effectTemplates_data = {
    "fader": {"type": "fader", "displayType": "Fader", "help": "The main fader for the channel",
              "params": {}
              },



 "rtplistener": {
        "type": "rtplistener",
        "displayType": "RTP Reciever",
        "help": "Recieve via RTP using the Opus codec",
        "gstElement": "rtpjitterbuffer",
        "params": {
            "latency": {
                "displayName":"Latency",
                "type": "float",
                "value": 100,
                "min": 5,
                "max":500,
                "step":1,
                "sort": 0
            },
             "preSupport.1.port": {
                "displayName": "Port",
                "type": "string.int",
                "value": 5000,
                "sort": 0
            }
            
        },
        "gstSetup": {},
        "sidechain": False,
        "preSupportElements": [
             
             #Whatever auto was in the channel before we have to just ignore, IceFlow will automatically not connect this to the next thing.
             {"gstElement": "fakesink", "gstSetup": 
             {
             }},

             {"gstElement": "udpsrc", "gstSetup": 
             {
                 'caps': "application/x-rtp, media=(string)audio, clock-rate=(int)48000, encoding-name=(string)X-GST-OPUS-DRAFT-SPITTKA-00, payload=(int)96, ssrc=(uint)950073154, clock-base=(uint)639610336, seqnum-base=(uint)55488" 
             }},
        ],
        "postSupportElements": [
            {"gstElement": "rtpopusdepay", "gstSetup": {}},
            {"gstElement": "opusdec", "gstSetup": {}},
             {"gstElement": "audioconvert", "gstSetup": {}},
             {"gstElement": "audioresample", "gstSetup": {}},

        ]
   },
   "rtpsender": {
        "type": "rtpsender",
        "displayType": "RTP Sender",
        "help": "Send via RTP using the Opus codec",
        "gstElement": "opusenc",
        "params": {
            "frame-size": {
                "displayName":"Frame Size",
                "type": "enum",
                "value": 20,
                "options":[["2.5ms",2], ['5ms',5], ["10ms",10], ["20ms",20], ["40ms",40], ["60ms",60]],
                "sort": 0
            },
            "bitrate": {
                "displayName":"Bit Rate",
                "type": "enum",
                "value": 128000,
                "options":[["16k",16000], ["48k",48000], ['64k',64000], ["128k",128000], ["192k",192000]],
                "sort": 0
            },
            "postSupport.1.host": {
                "displayName": "Host",
                "type": "string",
                "value": '127.0.0.1',
                "sort": 0
            },
            "postSupport.1.port": {
                "displayName": "Port",
                "type": "string.int",
                "value": 5000,
                "sort": 0
            }
            
        },
        "gstSetup": {},
        "sidechain": True,
        "preSupportElements": [
             {"gstElement": "audioconvert", "gstSetup": {}},
        ],
        "postSupportElements": [
             {"gstElement": "rtpopuspay", "gstSetup": {}},
             {"gstElement": "udpsink", "gstSetup": {}},
        ]
   },

   "a2dpsink": {
        "type": "a2dpsink",
        "displayType": "A2DP Sender",
        "help": "Send to a bluetooth speaker",
        "gstElement": "a2dpsink",
        "params": {
            "device": {
                "type": "string",
                "value": '',
                "sort": 0
            }
            
        },
        "gstSetup": {},
        "sidechain": True,
        "preSupportElements": [
            {"gstElement": "audioconvert", "gstSetup": {}},
            {"gstElement": "sbcenc", "gstSetup": {}},

            
        ]
    },
 "autotune": {
        "type": "autotune",
        "displayType": "Autotune",
        "help": "gareus-org-oss-lv2-fat1 chromatic scale",
        "monoGstElement": "gareus-org-oss-lv2-fat1",
        "params": {
            "corr": {
                "type": "float",
                "displayName": "Correction",
                "value": 1,
                "min": 0,
                "max": 1,
                "step": 0.1,
                "sort": 0
            },
            "bias": {
                "type": "float",
                "displayName": "Bias to current note",
                "value": 0.1,
                "min": 0,
                "max": 1,
                "step": 0.1,
                "sort": 0
            },
            "filter": {
                "type": "float",
                "displayName": "Filter",
                "value": 0.1,
                "min": 0.02,
                "max": 0.5,
                "step": 0.01,
                "sort": 0.001
            },
            "offset": {
                "type": "float",
                "displayName": "Shift",
                "value": 0,
                "min": -2,
                "max": 2,
                "step": 0.25,
                "sort": 0.25
            },
            
        },
        "gstSetup": {'m00':True,'m01':True,'m02':True,'m03':True,'m04':True,'m05':True,'m06':True,'m07':True,'m08':True,'m09':True,'m10':True,'m11':True},
        "sidechain": False,
        "preSupportElements": [
        ]
    },

 "ringmod": {
        "type": "ringmod",
        "displayType": "Ring Mod",
        "help": "Ring Modulation",
        "monoGstElement": "ladspa-ringmod-1188-so-ringmod-1i1o1l",
        "params": {
            "frequency": {
                "type": "float",
                "displayName": "Model",
                "value": 440,
                "min": 1,
                "max": 440,
                "step": 1,
                "sort": 0
            },
            "modulation-depth": {
                "type": "float",
                "displayName": "Deptch",
                "value": 0,
                "min": 0,
                "max": 2,
                "step": 1,
                "sort": 1
            },
            "sawtooth-level": {
                "type": "float",
                "displayName": "Saw",
                "value": 0,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 3
            },

            "square-level": {
                "type": "float",
                "displayName": "Square",
                "value": 0,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 3
            },
                        
            "sine-level": {
                "type": "float",
                "displayName": "Sine",
                "value": 1,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 2
            },
            "triangle-level": {
                "type": "float",
                "displayName": "Triangle",
                "value": 1,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 3
            }
        },
        "gstSetup": {},
        "sidechain": False,
        "preSupportElements": [
        ]
    },

    "audiotestsrc": {
        "type": "audiotestsrc",
        "displayType": "Noise generator",
        "help": "Noise generator",
        "monoGstElement": "audiotestsrc",
        "params": {
            "wave": {
                "type": "enum",
                "displayName": "Type",
                "value": 0,
                "options":[
                    ['sine',0],
                    ['white',5],
                    ['pink',6],
                    ['silence',0]

                ],
                "sort": 0
            }
        },
        "gstSetup": {},
        "sidechain": False,
        "noConnectInput": True,
        "preSupportElements": [
                        {"gstElement": "fakesink", "gstSetup": {}},

        ]
    },
    "swhmetronome": {
        "type": "swhmetronome",
        "displayType": "Metronome",
        "help": "SWH plugins metronome",
        "monoGstElement": "ladspasrc-caps-so-click",
        "params": {
            "model": {
                "type": "float",
                "displayName": "Model",
                "value": 0,
                "min": 0,
                "max": 3,
                "step": 1,
                "sort": 0
            },
            "bpm": {
                "type": "float",
                "displayName": "BPM",
                "value": 80,
                "min": -0,
                "max": 240,
                "step": 1,
                "sort": 1
            },
            "div": {
                "type": "float",
                "displayName": "Divisions",
                "value": 1,
                "min": 1,
                "max": 4,
                "step": 0.25,
                "sort": 1
            }
        },
        "gstSetup": {},
        "sidechain": False,
        "noConnectInput": True,
        "preSupportElements": [
                        {"gstElement": "fakesink", "gstSetup": {}},

        ]
    },


    "cabinet3": {
        "type": "cabinet3",
        "displayType": "Cabinet III",
        "help": "Amp cabinet sim",
        "monoGstElement": "ladspa-caps-so-cabinetiii",
        "params": {
            "model": {
                "type": "float",
                "displayName": "Model",
                "value": 0,
                "min": 0,
                "max": 16,
                "step": 1,
                "sort": 0
            },
            "gain": {
                "type": "float",
                "displayName": "Gain",
                "value": 0,
                "min": -24,
                "max": 24,
                "step": 0.25,
                "sort": 1
            }
        },
        "gstSetup": {},
        "sidechain": False,
        "preSupportElements": [
        ]
    },

    "ampvts": {
        "type": "ampvts",
        "displayType": "Amp VTS",
        "help": "CAPS Guitar amp sim(Heavy CPU?)",
        "monoGstElement": "ladspa-caps-so-ampvts",
        "params": {
            "over": {
                "type": "float",
                "displayName": "Oversampling",
                "value": 0,
                "min": 0,
                "max": 2,
                "step": 1,
                "sort": 0
            },
            "tonestack": {
                "type": "float",
                "displayName": "Tone Stack",
                "value": 0,
                "min": 0,
                "max": 8,
                "step": 1,
                "sort": 0
            },
            "gain": {
                "type": "float",
                "displayName": "Gain",
                "value": 0.25,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            },
            "bright": {
                "type": "float",
                "displayName": "Bright",
                "value": 0.75,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            },
            "power": {
                "type": "float",
                "displayName": "Power",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            },
            "bass": {
                "type": "float",
                "displayName": "Bass",
                "value": 0.25,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            },
            "mid": {
                "type": "float",
                "displayName": "Mid",
                "value": 0.75,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            },
            "treble": {
                "type": "float",
                "displayName": "Treble",
                "value": 1,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            },

            "attack": {
                "type": "float",
                "displayName": "Attack",
                "value": 0.25,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            },
            "squash": {
                "type": "float",
                "displayName": "Squash",
                "value": 0.75,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            },
            "lowcut": {
                "type": "float",
                "displayName": "Low Cut",
                "value": 0.75,
                "min": 0,
                "max": 1,
                "step": 0.025,
                "sort": 1
            }

        },
        "gstSetup": {},
        "sidechain": False,
        "preSupportElements": [
        ]
    },


    "valvesaturation": {
        "type": "valvesaturation",
        "displayType": "Valve Saturation",
        "help": "Steve Harris, Valve saturation (valve, 1209)",
        "monoGstElement": "ladspa-valve-1209-so-valve",
        "params": {
            "distortion-level": {
                "type": "float",
                "displayName": "Level",
                "value": 0,
                "min": 0,
                "max": 0.99,
                "step": 0.025,
                "sort": 0
            },
            "distortion-character": {
                "type": "float",
                "displayName": "Hardness",
                "value": 0,
                "min": 0,
                "max": 0.99,
                "step": 0.025,
                "sort": 1
            }
        },
        "gstSetup": {},
        "sidechain": False,
        "preSupportElements": [
        ]
    },

    "tonegenerator": {
        "type": "tonegenerator",
        "displayType": "Tone Generator",
        "help": "Tone gen",
        "gstElement": "audiotestsrc",
        "params": {
            "freq": {
                "type": "float",
                "displayName": "Frequency",
                "value": 440,
                "min": 10,
                "max": 20000,
                "sort": 0
            }
        },
        "gstSetup": {},
        "sidechain": False,
        "noConnectInput": True,
        "preSupportElements": [
            {"gstElement": "fakesink", "gstSetup": {}},
        ]
    },


    "speechrecognition": {
        "type": "speechrecognition",
        "displayType": "Speech Recognition",
        "help": "Speech Reecognition demo",
        "gstElement": "pocketsphinx",
        "params": {
        },
        "gstSetup": {},
        "sidechain": True,
        "preSupportElements": [
            {"gstElement": "audioconvert", "gstSetup": {}},
            {"gstElement": "audioresample", "gstSetup": {}},
        ]
    },

    "send": {
        "type": "send",
        "displayType": "Send",
        "help": "JACK mono/stereo send",
        "gstElement": "SpecialCase",
        "params": {
            "volume": {
                "type": "float",
                "displayName": "Level",
                "value": False,
                "sort": 0,
                "min": -60,
                "max": 0,
                "value": -60,
                "step": 1,
            },
            "*destination": {
                "type": "JackInput",
                "displayName": "Dest",
                "value": "",
                "sort": 1
            },
        }
    },

    "voicedsp": {
        "type": "voicedsp",
        "displayType": "Voice DSP",
        "help": "Noise Removal, AGC, and AEC",
        "gstElement": "webrtcdsp",

        "params": {
            "gain-control": {
                "type": "bool",
                "displayName": "AGC",
                "value": False,
                "sort": 0
            },
            "echo-cancel": {
                "type": "bool",
                "displayName": "Feedback Cancel",
                "value": True,
                "sort": 1
            },
            "noise-suppression":
            {
                "type": "bool",
                "displayName": "Noise Suppression",
                "value": True,
                "sort": 1
            }

        },
        "gstSetup": {
            "high-pass-filter": False,
            "delay-agnostic": True,
            'noise-suppression-level': 0
        },
        "preSupportElements": [
            {"gstElement": "queue", "gstSetup": {
                "min-threshold-time": 25*1000*000}},
            {"gstElement": "audioconvert", "gstSetup": {}},
            {"gstElement": "interleave", "gstSetup": {}}

        ],
        "postSupportElements": [
            {"gstElement": "audioconvert", "gstSetup": {}}
        ]
    },

    "voicedsprobe": {"type": "voicedsprobe", "displayType": "Voice DSP Probe", "help": "When using voice DSP, you must have one of these right before the main output.", "gstElement": "webrtcechoprobe",
                     "params": {}, "gstSetup": {},
                     "preSupportElements": [
                         {"gstElement": "audioconvert", "gstSetup": {}},
                         {"gstElement": "interleave", "gstSetup": {}}

                     ],
                     "postSupportElements": [
                         {"gstElement": "audioconvert", "gstSetup": {}}
                     ]
                     },
    "3beqp":
    {"type": "3beqp", "displayType": "3 Band Parametric EQ", "help": "Basic builtin paramentric EQ", "gstElement": "equalizer-nbands",
        "params": {
            "0:gain": {
                "type": "float",
                "displayName": "Low",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort": 3
            },

            "0:freq": {
                "type": "float",
                "displayName": "LowFreq",
                "value": 200,
                "min": 32,
                "max": 2000,
                "sort": 2.5
            },

            "0:bandwidth": {
                "type": "float",
                "displayName": "LowBW",
                "value": 200,
                "min": 50,
                "max": 1000,
                "sort": 2.3
            },

            "1:gain": {
                "type": "float",
                "displayName": "Mid",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort": 2
            },

            "1:freq": {
                "type": "float",
                "displayName": "MidFreq",
                "value": 2000,
                "min": 500,
                "max": 4000,
                "sort": 1.5
            },

            "1:bandwidth": {
                "type": "float",
                "displayName": "MidBW",
                "value": 2000,
                "min": 50,
                "max": 8000,
                "sort": 1
            },

            "2:gain": {
                "type": "float",
                "displayName": "High",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort": 0
            },
            "2:freq": {
                "type": "float",
                "displayName": "HighFreq",
                "value": 8000,
                "min": 4000,
                "max": 16000,
                "sort": 0.5
            },

            "2:bandwidth": {
                "type": "float",
                "displayName": "HighBW",
                "value": 2000,
                "min": 80,
                "max": 16000,
                "sort": 0
            },
        },
        "gstSetup":
        {
            "num-bands": 3,
            "0:freq": 180,
            "1:freq": 2000,
            "2:freq": 12000,
            "0:bandwidth": 360,
            "1:bandwidth": 500,
            "2:bandwidth": 16000,
        }
     },

    "3beq": {"type": "3beq", "displayType": "3 Band EQ", "help": "Basic builtin EQ", "gstElement": "equalizer-nbands",
             "params": {
                 "bypass": {
                     "type": "bool",
                     "displayName": "Bypass",
                     "value": False,
                     "sort": -1
                 },
                 "0:gain": {
                     "type": "float",
                     "displayName": "Low",
                     "value": 0,
                     "min": -12,
                     "max": 12,
                     "sort": 3
                 },
                 "1:gain": {
                     "type": "float",
                     "displayName": "Mid",
                     "value": 0,
                     "min": -12,
                     "max": 12,
                     "sort": 2
                 },

                 "1:freq": {
                     "type": "float",
                     "displayName": "MidFreq",
                     "value": 2000,
                     "min": 200,
                     "max": 8000,
                     "sort": 1
                 },

                 "2:gain": {
                     "type": "float",
                     "displayName": "High",
                     "value": 0,
                     "min": -12,
                     "max": 12,
                     "sort": 0
                 }
             },
             "gstSetup":
             {
                 "num-bands": 3,
                 "0:freq": 180,
                 "1:freq": 2000,
                 "2:freq": 12000,
                 "0:bandwidth": 360,
                 "1:bandwidth": 500,
                 "2:bandwidth": 16000,
             }
             },
    "plateReverb":
    {
        "displayType": "Plate Reverb",
        "type": "plateReverb",
        "monoGstElement": "ladspa-caps-so-plate",
        "stereoGstElement": "ladspa-caps-so-platex2",
        'help': "Basic plate reverb. From the CAPS plugins.",
        "params": {
            "blend": {
                "type": "float",
                "displayName": "Mix",
                "value": 0.25,
                "min": 0,
                "max": 1,
                "step": 0.01,
                "sort": 0
            },

            "bandwidth": {
                "type": "float",
                "displayName": "Bandwidth",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.01,
                "sort": 1
            },

            "tail": {
                "type": "float",
                "displayName": "Tail",
                "value": 0.75,
                "min": 0,
                "max": 1,
                "step": 0.01,
                "sort": 2
            },
            "damping": {
                "type": "float",
                "displayName": "Damping",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.01,
                "sort": 3
            }
        },
        "gstSetup":
            {},
    },
    "gverb":
    {
        "displayType": "GVerb",
        "type": "gverb",
        "gstElement": "ladspa-gverb-1216-so-gverb",
        'help': "Mono in stereo out GVerb(Steve Harris swh-plugins)",
        "params": {
            "roomsize": {
                "type": "float",
                "displayName": "Room Size",
                "value": 75,
                "min": 1,
                "max": 300,
                "step": 5,
                "sort": 0
            },

            "reverb-time": {
                "type": "float",
                "displayName": "Bandwidth",
                "value": 7.5,
                "min": 0.1,
                "max": 30,
                "step": 0.25,
                "sort": 1
            },

            "dry-signal-level": {
                "type": "float",
                "displayName": "Dry",
                "value": -70,
                "min": -70,
                "max": 0,
                "step": 1,
                "sort": 2
            },

            "early-reflection-level": {
                "type": "float",
                "displayName": "Early",
                "value": -70,
                "min": -70,
                "max": 0,
                "step": 1,
                "sort": 3
            },
            "tail-level": {
                "type": "float",
                "displayName": "Tail",
                "value": -70,
                "min": -70,
                "max": 0,
                "step": 1,
                "sort": 3
            },
            "damping": {
                "type": "float",
                "displayName": "Damping",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.01,
                "sort": 5
            }

        },
        "gstSetup":
            {},
        # It's stereo out, we may need to mono-ify it.
        "postSupportElements": [
            {"gstElement": "audioconvert", "gstSetup": {}}
        ],
        # It's mono in, maybe we need to downmix?
        "preSupportElements": [
            {"gstElement": "audioconvert", "gstSetup": {}}
        ]
    },

    "tenband":
    {
        "displayType": "10-Band EQ",
        "type": "tenband",
        "stereoGstElement": "ladspa-caps-so-eq10x2",
        'help': "Stereo 10-band (CAPS)",
        "params": {
            "param-31-hz": {
                "type": "float",
                "displayName": "31Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },

            "param-63-hz": {
                "type": "float",
                "displayName": "63Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },
            "param-125-hz": {
                "type": "float",
                "displayName": "125Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },
            "param-250-hz": {
                "type": "float",
                "displayName": "250Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },
            "param-500-hz": {
                "type": "float",
                "displayName": "500Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },
            "param-1-khz": {
                "type": "float",
                "displayName": "1KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },
            "param-2-khz": {
                "type": "float",
                "displayName": "2KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },
            "param-4-khz": {
                "type": "float",
                "displayName": "4KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },
            "param-8-khz": {
                "type": "float",
                "displayName": "8KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },
            "param-16-khz": {
                "type": "float",
                "displayName": "16KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step": 0.25,
                "sort": 0
            },

        },

        "gstSetup":
            {},

    },



    "tenband12db":
    {
        "displayType": "10-Band EQ(12db range)",
        "type": "tenband12db",
        "stereoGstElement": "ladspa-caps-so-eq10x2",
        'help': "Stereo 10-band (CAPS), +-12db per channel",
        "params": {
            "param-31-hz": {
                "type": "float",
                "displayName": "31Hz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },

            "param-63-hz": {
                "type": "float",
                "displayName": "63Hz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },
            "param-125-hz": {
                "type": "float",
                "displayName": "125Hz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },
            "param-250-hz": {
                "type": "float",
                "displayName": "250Hz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },
            "param-500-hz": {
                "type": "float",
                "displayName": "500Hz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },
            "param-1-khz": {
                "type": "float",
                "displayName": "1KHz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },
            "param-2-khz": {
                "type": "float",
                "displayName": "2KHz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },
            "param-4-khz": {
                "type": "float",
                "displayName": "4KHz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },
            "param-8-khz": {
                "type": "float",
                "displayName": "8KHz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },
            "param-16-khz": {
                "type": "float",
                "displayName": "16KHz",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 0.25,
                "sort": 0
            },

        },

        "gstSetup":
            {},

    },

    "sc1Compressor":
    {
        "type": "sc1Compressor",
        "displayType": "SC1 Compressor",
        "help": "Steve Harris SC1 compressor",
        "monoGstElement": "ladspa-sc1-1425-so-sc1",
        "params": {

            "threshold-level": {
                "type": "float",
                "displayName": "Threshold",
                "value": -12,
                "min": -30,
                "max": 0,
                "step": 0.01,
                "sort": 0
            },
            "attack-time": {
                "type": "float",
                "displayName": "Attack",
                "value": 100,
                "min": 1,
                "max": 400,
                "step": 0.01,
                "sort": 1
            },

            "release-time": {
                "type": "float",
                "displayName": "Release",
                "value": 200,
                "min": 0,
                "max": 800,
                "step": 0.01,
                "sort": 2
            },


            "ratio": {
                "type": "float",
                "displayName": "Ratio",
                "value": 2.5,
                "min": 0,
                "max": 10,
                "step": 0.1,
                "sort": 3
            },
            "knee-radius": {
                "type": "float",
                "displayName": "Knee",
                "value": 8,
                "min": 0,
                "max": 10,
                "step": 0.1,
                "sort": 4
            },
            "makeup-gain": {
                "type": "float",
                "displayName": "Gain",
                "value": 8,
                "min": 0,
                "max": 24,
                "step": 0.1,
                "sort": 5
            }

        },
        "gstSetup":
            {},
    },
    "echo":
    {
        "type": "echo",
        "gstElement": "audioecho",
        "help": "Simple echo",
        "displayType": "echo",
        "params": {

            "delay": {
                "type": "float",
                "displayName": "Delay",
                "value": 250,
                "min": 10,
                "max": 2500,
                "step": 10,
                "sort": 0
            },
            "intensity": {
                "type": "float",
                "displayName": "Mix",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.01,
                "sort": 1
            },
            "feedback": {
                "type": "float",
                "displayName": "feedback",
                "value": 0,
                "min": 0,
                "max": 1,
                "step": 0.01,
                "sort": 2
            },
        },
        'gstSetup': {
            "max-delay": 3000*1000*1000
        }
    },
    "volume":
    {
        "type": "volume",
        "gstElement": "volume",
        "help": "Volume Control(0 to 2)",
        "displayType": "Volume Control",
        "params": {

            "volume": {
                "type": "float",
                "displayName": "volume",
                "value": 1,
                "min": 0,
                "max": 2,
                "step": 0.01,
                "sort": 0
            },
        },
        'gstSetup': {
            "volume": 1
        }
    },
    "pitchshift":
    {
        "type": "pitchshift",
        "monoGstElement": "ladspa-tap-pitch-so-tap-pitch",
        "help": "Pitch shift(TAP LADSPA)",
        "displayType": "TAP Pitch Shifter",
        "params": {
            "semitone-shift": {
                "type": "float",
                "displayName": "Shift",
                "value": 0,
                "min": -12,
                "max": 12,
                "step": 1,
                "sort": 0
            },
            "dry-level": {
                "type": "float",
                "displayName": "Dry",
                "value": -90,
                "min": -90,
                "max": 20,
                "step": 1,
                "sort": 1
            },
            "wet-level": {
                "type": "float",
                "displayName": "Wet",
                "value": 0,
                "min": -90,
                "max": 20,
                "step": 1,
                "sort": 2
            },
        },
        'gstSetup': {
        }
    },

    "hqpitchshift":
    {
        "type": "hqpitchshift",
        "monoGstElement": "ladspa-pitch-scale-1194-so-pitchscalehq",
        "help": "Pitch shift(Steve Harris/swh-plugins)",
        "displayType": "FFT Pitch Shifter",
        "params": {
            "pitch-co-efficient": {
                "type": "float",
                "displayName": "Scale",
                "value": 0,
                "min": -2,
                "max": 2,
                "step": 0.01,
                "sort": 0
            },
        },
        'gstSetup': {
        }
    },

    "multichorus":
    {
        "type": "multichorus",
        "monoGstElement": "ladspa-multivoice-chorus-1201-so-multivoicechorus",
        "help": "Multivoice Chorus 1201 (Steve Harris/swh-plugins)",
        "displayType": "Multivoice Chorus",
        "params": {
            "number-of-voices": {
                "type": "float",
                "displayName": "Voices",
                "value": 1,
                "min": 1,
                "max": 8,
                "step": 1,
                "sort": 0
            },

            "delay-base": {
                "type": "float",
                "displayName": "Delay",
                "value": 10,
                "min": 10,
                "max": 40,
                "step": 1,
                "sort": 2
            },
            "voice-separation": {
                "type": "float",
                "displayName": "Separation",
                "value": 0.5,
                "min": 0,
                "max": 2,
                "step": 0.1,
                "sort": 3
            },

            "detune": {
                "type": "float",
                "displayName": "Detune",
                "value": 1,
                "min": 0,
                "max": 5,
                "step": 1,
                "sort": 4
            },
            "output-attenuation": {
                "type": "float",
                "displayName": "Level",
                "value": 1,
                "min": -20,
                "max": 0,
                "step": 1,
                "sort": 5
            },
        },
        'gstSetup': {
        }
    },

    "queue":
    {
        "type": "queue",
        "gstElement": "queue",
        "help": "Queue that enables multicore if placed before heavy effects.",
        "displayType": "queue",
        "params": {

            "min-threshold-time": {
                "type": "float",
                "displayName": "Delay",
                "value": 250,
                "min": 10,
                "max": 2500,
                "step": 10,
                "sort": 0
            },

        },
        'gstSetup': {
            "max-size-time": 5*1000*1000*1000,
            "leaky": 2
        }
    }

}
