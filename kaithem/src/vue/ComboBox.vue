<style scoped>
    .comboboxdropdown {
        background-color: rgb(235, 235, 235, 0.95);
        position: absolute;
        border-radius: 1em;
        border-style: solid;
        border-color:black;
        border-width:2px;
        max-height: 10em;
        overflow: scroll;
        min-width: 8em;
        z-index:100
    }
    .highlight
    {
        border-color:green;
    }
    
</style>

<template>
    <div style="display:inline-block;position:relative;" style="width:0px">
        <input v-bind:value="value" v-on:input="$emit('input', $event.target.value);focused=true" v-on:change="focused=false;$emit('change',$event.target.value);" v-on:focus="focused=true;">
        <button title="Show/Hide selector" v-on:click="showmenu=!showmenu;focused=false;" v-bind:class="{'highlight':showmenu}">...</button>
        <div v-if="showmenu||(focused)" class="comboboxdropdown">
            <div  v-for="i in pinned" v-if="(!value) || i[0].includes(value) || i[0].includes(value) || showmenu">
                <button v-on:click="$emit('input',i[0]);$emit('change',i[0]);showmenu=false;focused=false;" tabindex=-1 >{{i[0]}}</button><br>
                <p>{{i[1]}}</p>
            </div>

            <div  v-for="i in options" v-if="(!value) || i[0].includes(value) || i[0].includes(value) || showmenu">
                <button v-on:click="$emit('input',i[0]);$emit('change',i[0]);showmenu=false;focused=false;" tabindex=-1 >{{i[0]}}</button><br>
                <p>{{i[1]}}</p>
            </div>
        </div>
    </div>
</template>

<script>
    //Important note: There are two ways to open the menu. Clicking the menu button turns off filtering.
    module.exports = {

        props: {
        'pinned':{type:Array,default:function(){return []}},
        'options':{type:Array,default:function(){return []}},
        'value':{type:String,default:''}
        },
        name: 'ComboBox',
        data: function()
        {
            return (
                {
                   'showmenu':false,
                    focused:false
                })
        }
    }

</script>