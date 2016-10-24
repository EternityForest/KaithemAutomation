#This file uses pandoc to make MD versions
#Of the HTML docs. Maybe I should write in MD
#and compile to HTML, but for now, I'm doing this.

#Manually check output after running this,
#and always update it when you add any docs that should be md-ified
#And put into the repo root for easy online viewing

#set working dir
cd $(dirname $(realpath $0))
pandoc ../kaithem/src/html/help/help.html -t markdown_github -s -o  ../help.md
pandoc ../kaithem/src/html/help/changes.html -t markdown_github -s -o  ../changes.md
pandoc ../kaithem/src/html/help/license.html -t markdown_github -s -o  ../license.md
