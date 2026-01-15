<template>
  <div ref="container"></div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from "vue";

const properties = defineProps({
  schema: Object,
  modelValue: Object,
    options: Object,
  no_edit: Boolean
})

const emit = defineEmits(['update:modelValue', 'change', 'ready'])

const container = ref(null)
let editor = null
let blockOne = true

onMounted(() => {
    blockOne = true
  editor = new JSONEditor(container.value, {
    schema: properties.schema,
      startval: properties.modelValue,
    readOnly: properties.no_edit,
    ...properties.options
  })

    editor.on('change', () => {
        console.log('change')
        if (blockOne) { blockOne = false }
        else {

            emit('update:modelValue', editor.getValue())

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