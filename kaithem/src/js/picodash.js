import picodash from './thirdparty/picodash/picodash-base.esm.js'

class TagDataSource extends picodash.DataSource {
    async register() {

        async function upd(data) {
            this.data = data
            this.pushData(data)
        }
        this.sub = upd.bind(this)
        kaithemapi.subscribe(this.name, this.sub)

        var xmlhttp = new XMLHttpRequest();
        var url = "/tag_api/info" + this.name.split(":")[1];


        var this_ = this

        xmlhttp.onreadystatechange = function () {
            if (this.readyState == 4 && this.status == 200) {
                var myArr = JSON.parse(this.responseText);

                for (var i of ['min', 'max', 'hi', 'lo', 'step', 'unit']) {
                    if (myArr[i]) {
                        this_.config[i] = myArr[i]
                    }
                }
                this_.config.readonly = !myArr.writePermission

                this_.data = myArr.lastVal
                this_.ready()
            }
        };
        xmlhttp.open("GET", url, true);
        xmlhttp.send();
    }

    async pushData(d) {
        if (d != this.data) {
            this.data = d
            kaithemapi.sendValue(this.name, d)
        }
        super.pushData(d)
    }

    async getData() {
        return this.data
    }
    async close() {
        kaithemapi.unsubscribe(this.name, this.sub)
    }
}

picodash.addDataSourceProvider("tag", TagDataSource)


export default picodash