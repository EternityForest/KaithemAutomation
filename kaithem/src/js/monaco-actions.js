

String.prototype.replaceAll = function(search, replacement) {
    var target = this;
    return target.replace(new RegExp(search, 'gm'), replacement);
};

function add_actions(e)
{

}