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

String.prototype.replaceAll = function(search, replacement) {
    var target = this;
    return target.replace(new RegExp(search, 'gm'), replacement);
};

function add_mako_format(e)
{
    e.addAction({
	id: 'mako-format',
	label: 'Format Document(Preserve Mako Formatting, experimental)',
	contextMenuGroupId: '1_modification',
    contextMenuOrder: 1.9,
    
	run: function(ed) {
        var x = "\n"+ed.getValue()+"\n"
        var hide=[]
        var r = function(match, c)
        {
            hide.push(c)
            return("<mako-block-reference>"+hide.length+"</mako-block-reference>")
        }
        x = x.replaceAll(/^[\t ]*(\<\%(.|\w|\n)*?\%\>)\w*$/gm,r)

        x = x.replaceAll(/^[\t ]*(\%[\t ]*.*)$/gm,"<mako-literal>$1</mako-literal>")

        x=window.html_beautify(x,{
            "html": {
            "end_with_newline": true,
            "js": {
                "indent_size": 4
            },
            "css": {
                "indent_size": 4
            },
            "brace_style": "expand preserve-inline",
            "wrap_line_length":120,
        }})
        x = x.replaceAll(/\n?\<mako\-literal\>(.*?)\<\/mako-literal\>\n?/g,"\n$1\n")
        x = x.replaceAll(/\n?\<mako\-literal\>(.*?)\<\/mako-literal\>\n?/g,"\n$1\n")
        x = x.replaceAll(/\<mako\-block\-reference\>[\n\t\r ]*(\d*)[\n\t\r ]*\<\/mako\-block\-reference\>/g,
        (m,n)=> hide[parseInt(n)-1])
        ed.executeEdits('beautifier', [{ identifier: 'insert', range: new monaco.Range(1, 1, 10000000, 1), text: x, forceMoveMarkers: false }]);

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