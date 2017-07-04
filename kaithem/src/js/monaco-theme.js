require(['vs/editor/editor.main'], function() {
    monaco.editor.defineTheme('kaithem', {
                base: 'vs', // can also be vs-dark or hc-black
                inherit: true, // can also be false to completely replace the builtin rules
                rules: [
                    { token: 'attribute.name', foreground: '006050'},
                    { token: 'attribute.value.html', foreground: '3070f0'},
                    { token: 'keyword.python', foreground: '3070f0'}
                ]
            })});