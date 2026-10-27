// Preprocesses a JSON Editor schema so that any string text input with an
// "examples" array gets a <datalist> of suggestions attached to it.
// The datalist is wired up through the schema's options.inputAttributes.list,
// which the bundled json-editor applies to the underlying <input> element.
function kaithemAddExampleDatalists(schema) {
    let counter = 0

    function walk(node) {
        if (Array.isArray(node)) {
            for (const i of node) {
                walk(i)
            }
            return
        }

        if (!node || typeof node !== 'object') {
            return
        }

        // Only plain string text inputs (not enums/selects) get a datalist.
        if (
            node.type === 'string' &&
            !node.enum &&
            Array.isArray(node.examples) &&
            node.examples.length > 0
        ) {
            const id = 'kaithem-examples-' + counter++

            const datalist = document.createElement('datalist')
            datalist.id = id
            for (const example of node.examples) {
                const option = document.createElement('option')
                option.value = example
                datalist.append(option)
            }
            document.body.append(datalist)

            node.options = node.options || {}
            node.options.inputAttributes = node.options.inputAttributes || {}
            node.options.inputAttributes.list = id
        }

        for (const key of Object.keys(node)) {
            walk(node[key])
        }
    }

    walk(schema)
    return schema
}

globalThis.kaithemAddExampleDatalists = kaithemAddExampleDatalists
