<%
    import json
%>
%if not __jsvars__ == undefined:
%for i in __jsvars__:
${i} = ${json.dumps(__jsvars__[i])}
%endfor
%endif