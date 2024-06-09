<template id="smooth-range">
    <input type="range" :value="_val" @input="onInput" @change="onInput"
    :max="max" :min="min" :disabled="disabled"/>
</template>

<script>

export default {
  template: '#smooth-range',
  data: function () {
    const v = this.modelValue
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
    }
  },
  watch: {
    modelValue(newVal) {
      newVal=parseFloat(newVal)
      if (newVal !== this._val) {
        this.trySetValue(newVal)
      }
    }
  },
  methods: {
    trySetValue(newVal) {
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
        this.$emit('update:modelValue', this._val);
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
      const newValue = event.target.value;
      this._val = newValue
      this.trySendVal()
    }
  }
}
</script>