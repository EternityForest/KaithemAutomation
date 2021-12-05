const VueAceEditor = {
    //  simplified model handling using `value` prop and `input` event for $emit 
    props:['value','id','options'],

    //  add dynmic class and id (if not set) based on component tag
    template:`
        <div :id="id ? id: $options._componentTag +'-'+ _uid" 
            :class="$options._componentTag">
            <slot></slot>
        </div>
    `,

    watch:{
        value(){
            //This is the forward 
            //  update value on external model changes
            if(this.oldValue !== this.value){ 
                this.oldValue=this.value;
                if(this.ivalue !== this.value){
                    if(1)//if(!this.locked)
                    {
                        this.editor.setValue(this.value, 1);
                        return;
                    }
                }
            }
            //We don't accept the change, so we emit an event to change it back
            this.$emit('input', this.ivalue);
        }
    },

    mounted(){
        //  editor
        this.editor = window.ace.edit(this.$el.id);
        
        //  deprecation fix
        this.editor.$blockScrolling = Infinity;
        this.locked =0     

        //  ignore doctype warnings
        const session = this.editor.getSession();
        session.on("changeAnnotation", () => {
            const a = session.getAnnotations();
            const b = a.slice(0).filter( (item) => item.text.indexOf('DOC') == -1 );
            if(a.length > b.length) session.setAnnotations(b);
        });

        //  editor options 
        //  https://github.com/ajaxorg/ace/wiki/Configuring-Ace
        this.options = this.options || {};
        
        //  opinionated option defaults
        this.options.maxLines = this.options.maxLines || Infinity;
        this.options.printMargin = this.options.printMargin || false;      
        this.options.highlightActiveLine = this.options.highlightActiveLine || false;

        //  hide cursor 
        if(this.options.cursor === 'none' || this.options.cursor === false){
            this.editor.renderer.$cursorLayer.element.style.display = 'none';
            delete this.options.cursor; 
        }

        //  add missing mode and theme paths 
        if(this.options.mode && this.options.mode.indexOf('ace/mode/')===-1) {
            this.options.mode = 'ace/mode/'+this.options.mode;
        }
        if(this.options.theme && this.options.theme.indexOf('ace/theme/')===-1) {
            this.options.theme = 'ace/theme/'+this.options.theme;
        }
        this.editor.setOptions(this.options);
        
        
        //  set model value 
        //  if no model value found – use slot content
        if(!this.value || this.value === ''){
            this.$emit('input', this.editor.getValue());
            this.$emit('change', this.editor.getValue());
            this.ivalue = this.ivalue = this.oldValue = this.editor.getValue();
        } else {
            this.editor.setValue(this.value, -1);
            this.ivalue = this.oldValue = this.value;
        }        
        
        //  editor value changes   
        this.editor.on('change', (e) => {
            //  oldValue set to prevent internal updates
            this.ivalue = this.oldValue = this.editor.getValue();
        });
        //  editor value changes   
        this.editor.on('input', (e) => {
            //  oldValue set to prevent internal updates
            this.locked =1;
            this.ivalue = this.oldValue = this.editor.getValue();
            this.$emit('input', this.ivalue);
        });
         //  editor value changes   
        this.editor.on('blur', () => {
            this.$emit('change', this.ivalue);
            this.locked =0;
        });

    },
    methods: { editor(){ return this.editor } }
};