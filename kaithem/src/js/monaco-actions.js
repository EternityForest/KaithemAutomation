var insert =function(editor,text)
    {
        var line = editor.getPosition();
        var range = new monaco.Range(line.lineNumber, 1, line.lineNumber, 1);
        var id = { major: 1, minor: 1 };             
        var op = {identifier: id, range: range, text: text, forceMoveMarkers: true};
        editor.executeEdits("my-source", [op]);
    }



function escws(s)
        {   
            //all runs of whitespace get paren-ified
            var s=s.replace(/[\t ]*/,"($1)")

            //Double all real backticks, we will use single backticks as our
            //escape symbol for a newline
            var s=s.replace("`","``")
            var s=s.replace("\n","`n")
            var s=s.replace("\r","`r")
            return "<mako-literal>"+s+"</mako-literal>"
        }


function unescws(s)
        {   
            return s

            var s=s.replace(/\([\t ]\)*/,"$1")
            var s=s.replace("`n","\n")
            var s=s.replace("`r","\r")
            //Remaining double backticks are real
            var s=s.replace("``","`")
        }

function add_mako_format(e)
{
    e.addAction({
	id: 'format-id',
	label: 'Format',
	contextMenuGroupId: 'edit',
	contextMenuOrder: 1.9,

	run: function(ed) {
		var x = ed.getValue();
        x = x.replace(/\n(\%[\t ]*.*)\n/g,"<mako-literal>$1</mako-literal>")
        x = tidy_html5(x,{"indent":true,"show-body-only":true,"wrap-asp":false, "new-inline-tags":"mako-literal"})
        x = x.replace(/(.)\<mako\-literal\>/g,"$1\n<mako-literal>")
        x = x.replace(/\<mako\-literal\>(.*?)\<\/mako-literal\>/g,"$1\n")
        ed.setValue(x)
		return null;
	}
});


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