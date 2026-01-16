<template>
  <div class="window paper" id="app">
    <h2>UseOPZDMX</h2>
    <p>This app allows you to import fixtures from a file in OP-Z format, such as those availble from the <a href="https://open-fixture-library.org/">OFL</a>.
    Simply upload your file, select a fixture type, and import it.
    </p>
    <p>Kaithem currently does not support fixtures with multiple modes, each mode is treated as a separate type.</p>

    <div style="display:flex">
      <div>
        <input id="file" type="file" @change="onChange" />
        <label>Search:<input v-model="search" /></label>
        <ul v-if="d['profiles']">
          <li v-for="(v, i) of d['profiles']" :key="i" v-if="v['name'].includes(search)">
            <button @click="selected = v">{{ v['name'] }}</button>
          </li>
        </ul>
      </div>

      <div style="border: 1px solid; width:20em;">
        <h3>Channels</h3>
        <table border="1" v-if="selected['channels']">
          <tr v-for="(v, i) of selected['channels']" :key="i">
            <td>{{ i }}</td>
            <td>{{ v }}</td>
          </tr>
        </table>
        <button @click="importfixture()">Import Fixture Definition</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'

const selected = ref({})
const search = ref('')
const d = ref({})

const onChange = (event) => {
  const reader = new FileReader()
  reader.onload = onReaderLoad
  reader.readAsText(event.target.files[0])
}

const onReaderLoad = (event) => {
  console.log(event.target.result)
  d.value = JSON.parse(event.target.result)
}

const importfixture = () => {
  api_link.send(['setfixtureclassopz', selected.value['name'], selected.value])
}
</script>

<style scoped>
</style>
