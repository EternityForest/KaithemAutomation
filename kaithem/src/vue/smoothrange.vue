<template id="smooth-range">
    <input type="range"
    @input="onInput" 
    @change="onInput"
    :title="title"
    :max="max" 
    :min="min" 
    :disabled="disabled"
    v-model="_val" 
    />
</template>

<script>

export default {
  template: '#smooth-range',
  data: function () {
    const v = parseFloat(this.modelValue)
    return ({
      _val: v,
      lastUserChange: 0,
      bgWorker: null,
      lastSend: 0
    })
  },
  props: {
    modelValue: {
      required: true
    },
    min: {
      required: true
    },
    max: {
      required: true
    },
    disabled: {
      default: false
    },
    title: {
      default: ""
    }
  },
  watch: {
    modelValue(newVal) {
      newVal=parseFloat(newVal)
        this.trySetValue(newVal)
    }
  },
  methods: {
    trySetValue(newVal) {
      newVal=parseFloat(newVal)
      if (this.bgWorker) {
          clearTimeout(this.bgWorker);
          this.bgWorker = null;
        }
      if (newVal == this._val) {
        return
      }
      // If uesr has not recently interacted, set now.
      // Otherwise, set 600ms after the last user interaction
      if (Date.now() - this.lastUserChange > 600) {
        this._val = newVal
      }
      else {


        this.bgWorker = setTimeout(() => {
          this.bgWorker = null
          this.trySetValue(newVal)
        }, 200)

      }
    },


    trySendVal() {
      if (this.bgWorkerSend) {
          clearTimeout(this.bgWorkerSend);
          this.bgWorkerSend = null;
      }
        
      // If uesr has not recently interacted, set now.
      // Otherwise, set 600ms after the last user interaction
      if (Date.now() - this.lastSend > 44) {
        this.lastSend = Date.now()
        this.$emit('update:modelValue', parseFloat(this._val));
      }
      else {


        this.bgWorkerSend = setTimeout(() => {
          this.bgWorkerSend = null
          this.trySendVal()
        }, 30)

      }
    },
    onInput(event) {
  
      this.lastUserChange = Date.now()
      const newValue = parseFloat(event.target.value);
      this._val = newValue
      this.trySendVal()
    }
  }
}
</script>