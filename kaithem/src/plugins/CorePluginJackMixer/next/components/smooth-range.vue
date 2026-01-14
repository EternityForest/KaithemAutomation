<template>
    <input
        type="range"
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

<script setup lang="ts">
import { ref, watch } from 'vue';

const properties = defineProps<{
    modelValue: number;
    min: number;
    max: number;
    step?: number;
    disabled?: boolean;
    title?: string;
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: number): void;
}>();

const _val = ref(Number.parseFloat(String(properties.modelValue)));
const lastUserChange = ref(0);
const bgWorker = ref<number | null>(null);
const lastSend = ref(0);
const _min = ref(properties.min);
const _max = ref(properties.max);
const bgWorkerSend = ref<number | null>(null);

watch(() => properties.modelValue, (newValue) => {
    trySetValue(Number.parseFloat(String(newValue)));
});

watch(() => properties.min, (newValue) => {
    _min.value = newValue;
});

watch(() => properties.max, (newValue) => {
    _max.value = newValue;
});

function trySetValue(newValue: number) {
    if (bgWorker.value) {
        clearTimeout(bgWorker.value);
        bgWorker.value = null;
    }

    if (newValue === _val.value) {
        return;
    }

    // If user has not recently interacted, set now.
    // Otherwise, set 600ms after the last user interaction
    if (Date.now() - lastUserChange.value > 600) {
        // Expand range if commanded by server
        if (newValue < _min.value) {
            _min.value = newValue;
        }
        if (newValue > _max.value) {
            _max.value = newValue;
        }
        // Work around val being updated before min and max
        setTimeout(() => {
            _val.value = newValue;
        }, 5);
    } else {
        bgWorker.value = globalThis.setTimeout(() => {
            bgWorker.value = null;
            trySetValue(newValue);
        }, 200);
    }
}

function trySendValue() {
    if (bgWorkerSend.value) {
        clearTimeout(bgWorkerSend.value);
        bgWorkerSend.value = null;
    }

    // If user has not recently interacted, send now.
    // Otherwise, send 44ms after the last send
    if (Date.now() - lastSend.value > 44) {
        lastSend.value = Date.now();
        emit('update:modelValue', Number.parseFloat(String(_val.value)));
    } else {
        bgWorkerSend.value = globalThis.setTimeout(() => {
            bgWorkerSend.value = null;
            trySendValue();
        }, 30);
    }
}

function onInput(event: Event) {
    lastUserChange.value = Date.now();
    const target = event.target as HTMLInputElement;
    const newValue = Number.parseFloat(target.value);
    _val.value = newValue;
    trySendValue();
}
</script>
