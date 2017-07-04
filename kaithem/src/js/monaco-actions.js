var insert =function(editor,text)
    {
        var line = editor.getPosition();
        var range = new monaco.Range(line.lineNumber, 1, line.lineNumber, 1);
        var id = { major: 1, minor: 1 };             
        var op = {identifier: id, range: range, text: text, forceMoveMarkers: true};
        editor.executeEdits("my-source", [op]);
    }


function add_actions(e)
{
    e.addAction({
	id: 'copy-id',
	label: 'Copy',
	contextMenuGroupId: 'edit',
	contextMenuOrder: 1.5,

	run: function(ed) {
		document.execCommand("copy")
		return null;
	}
});

    e.addAction({
	id: 'cut-id',
	label: 'Cut',
	contextMenuGroupId: 'edit',
	contextMenuOrder: 1.6,

	run: function(ed) {
		document.execCommand("cut")
		return null;
	}
});

    e.addAction({
	id: 'comment-id',
	label: 'Toggle Comments',
	contextMenuGroupId: 'edit',
	contextMenuOrder: 1.7,
	run: function(ed) {
        var s = ed.getSelection()
        if (s.startLineNumber == s.endLineNumber)
        {
            ed.getAction('editor.action.commentLine').run()
        }
        else
        {
            var a= ed.getAction('editor.action.commentBlock')
            if(a)
            {
                a.run()
            }
            else{
                ed.getAction('editor.action.commentLine').run()
            }
        }
    		return null;
	}
});
}