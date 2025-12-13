<template>
  <div ref="container"></div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from "/static/js/thirdparty/vue.esm-browser.js";

const properties = defineProps({
  schema: Object,
  modelValue: Object,
  options: Object
})

const emit = defineEmits(['update:modelValue', 'change', 'ready'])

const container = ref(null)
let editor = null
let blockOne = true

onMounted(() => {
  editor = new JSONEditor(container.value, {
    schema: properties.schema,
    startval: properties.modelValue,
    ...properties.options
  })

    editor.on('change', () => {
        emit('update:modelValue', editor.getValue())
        if (blockOne) { blockOne = false }
        else {
            emit('change', editor.getValue())
        }
  })

  emit('ready', editor)
})

watch(
  () => properties.modelValue,
    (value) => {
    
        if (editor) {
            blockOne = true
            editor.setValue(value)
        }
  },
  { deep: true }
)

watch(
  () => properties.schema,
  (schema) => {
    if (editor) editor.destroy()
    editor = new JSONEditor(container.value, {
      schema,
      startval: properties.modelValue,
      ...properties.options
    })
  }
)

onBeforeUnmount(() => {
  if (editor) editor.destroy()
})
</script>