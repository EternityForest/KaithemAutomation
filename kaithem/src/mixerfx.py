#These are templates for effect data. Note that they contain everything needed to generate and interface for
#And use a gstreamer element. Except fader, which is special cased.
effectTemplates_data={
    "fader":{"type":"fader", "displayType": "Fader", "help": "The main fader for the channel",
    "params": {}
    },


    "send":{
        "type":"send", 
        "displayType":"Send",
        "help": "JACK mono/stereo send", 
        "gstElement": "SpecialCase",
        "params": {
          "volume": {
                "type":"float",
                "displayName": "Level",
                "value": False,
                "sort":0,
                "min":-60,
                "max":0,
                "value":-60,
                "step":1,
            },
          "*destination": {
                "type":"JackInput",
                "displayName": "Dest",
                "value": "",
                "sort":1
            },
        }
    },

    "voicedsp":{
        "type":"voicedsp", 
        "displayType":"Voice DSP",
        "help": "Noise Removal, AGC, and AEC", 
        "gstElement": "webrtcdsp",
        
        "params": {
          "gain-control": {
                "type":"bool",
                "displayName": "AGC",
                "value": False,
                "sort":0
            },
          "echo-cancel": {
                "type":"bool",
                "displayName": "Feedback Cancel",
                "value": True,
                "sort":1
            },
           "noise-suppression":
           {
                "type":"bool",
                "displayName": "Noise Suppression",
                "value": True,
                "sort":1          
            }

        },
        "gstSetup":{
            "high-pass-filter": False,
            "delay-agnostic": True,
            'noise-suppression-level': 0
        },
        "preSupportElements":[
            {"gstElement": "queue", "gstSetup":{"min-threshold-time": 25*1000*000}},
            {"gstElement": "audioconvert", "gstSetup":{}},
            {"gstElement": "interleave", "gstSetup":{}}

        ],
        "postSupportElements":[
            {"gstElement": "audioconvert", "gstSetup":{}}
        ]
    },

    "voicedsprobe":{"type":"voicedsprobe", "displayType":"Voice DSP Probe","help": "When using voice DSP, you must have one of these right before the main output.", "gstElement": "webrtcechoprobe",
    "params":{}, "gstSetup":{},
     "preSupportElements":[
        {"gstElement": "audioconvert", "gstSetup":{}},
        {"gstElement": "interleave", "gstSetup":{}}

        ],
    "postSupportElements":[
        {"gstElement": "audioconvert", "gstSetup":{}}
    ]
    },

    "3beq":{"type":"3beq", "displayType":"3 Band EQ","help": "Basic builtin EQ", "gstElement": "equalizer-nbands",
        "params": {
          "0:gain": {
                "type":"float",
                "displayName": "Low",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort":3
            },
            "1:gain": {
                "type":"float",
                "displayName": "Mid",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort":2
            },

            "1:freq": {
                "type":"float",
                "displayName": "MidFreq",
                "value": 0,
                "min": 200,
                "max": 8000,
                "sort":1
            },
          
            "2:gain": {
                "type":"float",
                "displayName": "High",
                "value": 0,
                "min": -12,
                "max": 12,
                "sort":0
            }
        },
        "gstSetup":
        {
            "num-bands":3,
            "band1::freq": 180,
            "band2::freq": 2000,
            "band3::freq": 12000,
            "band1::bandwidth": 360,
            "band2::bandwidth": 3600,
            "band3::bandwidth": 19000,
        }
    },
    "plateReverb":
    {
        "displayType":"Plate Reverb",
        "type": "plateReverb",
        "monoGstElement": "ladspa-caps-so-plate",
        "stereoGstElement": "ladspa-caps-so-platex2",
        'help': "Basic plate reverb. From the CAPS plugins.",
        "params": {
          "blend": {
                "type":"float",
                "displayName": "Mix",
                "value": 0.25,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":0
            },

            "bandwidth": {
                "type":"float",
                "displayName": "Bandwidth",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":1
            },

            "tail": {
                "type":"float",
                "displayName": "Tail",
                "value": 0.75,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":2
            },
            "damping": {
                "type":"float",
                "displayName": "Damping",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":3
            }
        },
          "gstSetup":
            {},
    },
    "gverb":
    {
        "displayType":"GVerb",
        "type": "gverb",
        "gstElement": "ladspa-gverb-1216-so-gverb",
        'help': "Mono in stereo out GVerb(Steve Harris swh-plugins)",
        "params": {
          "roomsize": {
                "type":"float",
                "displayName": "Room Size",
                "value": 75,
                "min": 1,
                "max": 300,
                "step":5,
                "sort":0
            },

            "reverb-time": {
                "type":"float",
                "displayName": "Bandwidth",
                "value": 7.5,
                "min": 0.1,
                "max": 30,
                "step":0.25,
                "sort":1
            },

            "dry-signal-level": {
                "type":"float",
                "displayName": "Dry",
                "value": -70,
                "min": -70,
                "max": 0,
                "step":1,
                "sort":2
            },

            "early-reflection-level": {
                "type":"float",
                "displayName": "Early",
                "value": -70,
                "min": -70,
                "max": 0,
                "step":1,
                "sort":3
            },
            "tail-level": {
                "type":"float",
                "displayName": "Tail",
                "value": -70,
                "min": -70,
                "max": 0,
                "step":1,
                "sort":3
            },
            "damping": {
                "type":"float",
                "displayName": "Damping",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":5
            }

            },
              "gstSetup":
            {},
        #It's stereo out, we may need to mono-ify it.
        "postSupportElements":[
            {"gstElement": "audioconvert", "gstSetup":{}}
        ],
        #It's mono in, maybe we need to downmix?
        "preSupportElements":[
            {"gstElement": "audioconvert", "gstSetup":{}}
        ]
    },

    "tenband":
    {
        "displayType":"10-Band EQ",
        "type": "gverb",
        "stereoGstElement": "ladspa-caps-so-eq10x2",
        'help': "Stereo 10-band (CAPS)",
        "params": {
          "param-31-hz": {
                "type":"float",
                "displayName": "31Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },

          "param-63-hz": {
                "type":"float",
                "displayName": "63Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },
          "param-125-hz": {
                "type":"float",
                "displayName": "125Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },
          "param-250-hz": {
                "type":"float",
                "displayName": "250Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },
          "param-500-hz": {
                "type":"float",
                "displayName": "500Hz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },
          "param-1-khz": {
                "type":"float",
                "displayName": "1KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },
          "param-2-khz": {
                "type":"float",
                "displayName": "2KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },
          "param-4-khz": {
                "type":"float",
                "displayName": "4KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },
          "param-8-khz": {
                "type":"float",
                "displayName": "8KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },
          "param-16-hz": {
                "type":"float",
                "displayName": "16KHz",
                "value": 0,
                "min": -48,
                "max": 24,
                "step":0.25,
                "sort":0
            },

            },

    "gstSetup":
            {},
       
    },

    "sc1Compressor":
    {
        "type": "sc1Compressor",
        "displayType":"SC1 Compressor",
        "help": "Steve Harris SC1 compressor",
        "monoGstElement": "ladspa-sc1-1425-so-sc1",
        "params": {

            "threshold-level": {
                "type":"float",
                "displayName": "Threshold",
                "value": -12,
                "min": -30,
                "max": 0,
                "step":0.01,
                "sort":0
            },
          "attack-time": {
                "type":"float",
                "displayName": "Attack",
                "value": 100,
                "min": 1,
                "max": 400,
                "step":0.01,
                "sort":1
            },

            "release-time": {
                "type":"float",
                "displayName": "Release",
                "value":200,
                "min": 0,
                "max": 800,
                "step":0.01,
                "sort":2
            },

            
            "ratio": {
                "type":"float",
                "displayName": "Ratio",
                "value": 2.5,
                "min": 0,
                "max": 10,
                "step":0.1,
                "sort":3
            },
            "knee-radius": {
                "type":"float",
                "displayName": "Knee",
                "value": 8,
                "min": 0,
                "max": 10,
                "step":0.1,
                "sort":4
            },
            "makeup-gain": {
                "type":"float",
                "displayName": "Gain",
                "value": 8,
                "min": 0,
                "max": 24,
                "step":0.1,
                "sort":5
            }

            },
      "gstSetup":
            {},
    },
    "echo":
    {
        "type": "echo",
        "gstElement":"audioecho",
        "help":"Simple echo",
        "displayType":"echo",
        "params": {

            "delay": {
                "type":"float",
                "displayName": "Delay",
                "value": 250,
                "min": 10,
                "max": 2500,
                "step":10,
                "sort":0
            },
          "intensity": {
                "type":"float",
                "displayName": "Mix",
                "value": 0.5,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":1
            },
         "feedback": {
                "type":"float",
                "displayName": "feedback",
                "value": 0,
                "min": 0,
                "max": 1,
                "step":0.01,
                "sort":2
            },
        },
        'gstSetup':{
            "max-delay":3000*1000*1000
        }
    },

    "pitchshift":
    {
        "type": "pitchshift",
        "monoGstElement":"ladspa-tap-pitch-so-tap-pitch",
        "help":"Pitch shift(TAP LADSPA)",
        "displayType":"TAP Pitch Shifter",
        "params": {
            "semitone-shift": {
                "type":"float",
                "displayName": "Shift",
                "value": 0,
                "min": -12,
                "max": 12,
                "step":1,
                "sort":0
            },
          "dry-level": {
                "type":"float",
                "displayName": "Dry",
                "value": -90,
                "min": -90,
                "max": 20,
                "step":1,
                "sort":1
            },
         "wet-level": {
                "type":"float",
                "displayName": "Wet",
                "value": 0,
                "min": -90,
                "max": 20,
                "step":1,
                "sort":2
            },
        },
        'gstSetup':{
        }
    },

    "hqpitchshift":
    {
        "type": "hqpitchshift",
        "monoGstElement":"ladspa-pitch-scale-1194-so-pitchscalehq",
        "help":"Pitch shift(Steve Harris/swh-plugins)",
        "displayType":"FFT Pitch Shifter",
        "params": {
            "pitch-co-efficient": {
                "type":"float",
                "displayName": "Scale",
                "value": 0,
                "min": -2,
                "max": 2,
                "step":0.01,
                "sort":0
            },
        },
        'gstSetup':{
        }
    },

    "multichorus":
    {
        "type": "multichorus",
        "monoGstElement":"ladspa-multivoice-chorus-1201-so-multivoicechorus",
        "help":"Multivoice Chorus 1201 (Steve Harris/swh-plugins)",
        "displayType":"Multivoice Chorus",
        "params": {
            "number-of-voices": {
                "type":"float",
                "displayName": "Voices",
                "value": 1,
                "min": 1,
                "max": 8,
                "step":1,
                "sort":0
            },
 
            "delay-base": {
                "type":"float",
                "displayName": "Delay",
                "value": 10,
                "min": 10,
                "max": 40,
                "step":1,
                "sort":2
            },
            "voice-separation": {
                "type":"float",
                "displayName": "Separation",
                "value": 0.5,
                "min": 0,
                "max": 2,
                "step":0.1,
                "sort":3
            },

            "detune": {
                "type":"float",
                "displayName": "Detune",
                "value": 1,
                "min": 0,
                "max": 5,
                "step":1,
                "sort":4
            },
            "output-attenuation": {
                "type":"float",
                "displayName": "Level",
                "value": 1,
                "min": -20,
                "max": 0,
                "step":1,
                "sort":5
            },
        },
        'gstSetup':{
        }
    },

   "queue":
    {
        "type": "queue",
        "gstElement":"queue",
        "help":"Queue that enables multicore if placed before heavy effects.",
        "displayType":"queue",
        "params": {

            "min-threshold-time": {
                "type":"float",
                "displayName": "Delay",
                "value": 250,
                "min": 10,
                "max": 2500,
                "step":10,
                "sort":0
            },

        },
        'gstSetup':{
            "max-size-time": 5*1000*1000*1000,
            "leaky":2
        }
    }

}