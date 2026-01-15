<template id="smooth-range">
    <input type="range"
    @input="onInput" 
    @change="onInput"
    :title="title"
    :max="_max" 
    :min="_min" 
    :disabled="disabled"
    :step="step"
    v-model="_val" 
    />
</template>

<script>

export default {
  template: '#smooth-range',
  data: function () {
    const v = Number.parseFloat(this.modelValue)
    return ({
      _val: v,
      lastUserChange: 0,
      bgWorker: null,
      lastSend: 0,
      _min:this.min,
      _max:this.max
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
    step: {
      default: 1
    },
    disabled: {
      default: false
    },
    title: {
      default: ""
    }
  },
  watch: {
    modelValue(newValue) {
      newValue=Number.parseFloat(newValue)
        this.trySetValue(newValue)
    },
    min(newValue) {
      this._min=newValue
    },
    max(newValue) {
      this._max=newValue
    }
  },
  methods: {
    trySetValue(newValue) {
      console.log(newValue)
      newValue=Number.parseFloat(newValue)
      if (this.bgWorker) {
          clearTimeout(this.bgWorker);
          this.bgWorker = null;
        }
      if (newValue == this._val) {
        return
      }
      // If user has not recently interacted, set now.
      // Otherwise, set 600ms after the last user interaction
      if (Date.now() - this.lastUserChange > 600) {
        // Expand range if commanded by server
        // In case something updates val before min/max
        if (newValue < this._min) {
          this._min = newValue
        }
        if (newValue > this._max) {
          this._max = newValue
        }
        // Work around val being updated before min and max
        setTimeout(() => {
                  this._val = newValue
        },5)
      }
      else {


        this.bgWorker = setTimeout(() => {
          this.bgWorker = null
          this.trySetValue(newValue)
        }, 200)

      }
    },


    trySendVal() {
      if (this.bgWorkerSend) {
          clearTimeout(this.bgWorkerSend);
          this.bgWorkerSend = null;
      }
        
      // If user has not recently interacted, set now.
      // Otherwise, set 600ms after the last user interaction
      if (Date.now() - this.lastSend > 44) {
        this.lastSend = Date.now()
        this.$emit('update:modelValue', Number.parseFloat(this._val));
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
      const newValue = Number.parseFloat(event.target.value);
      this._val = newValue
      this.trySendVal()
    }
  }
}
</script>