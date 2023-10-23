<template>
    <Story title="components/TextareaMd" :layout="{ type: 'single', iframe: true }">
        <Variant title="Default" :init-state="stateDefault" auto-props-disabled>
            <template #default="{ state }">
                <TextareaMd :id="state.id" :label="state.label" :color="state.color" v-model="state.content" />
            </template>
            <template #controls="{ state }">
                <HstText v-model="state.content" title="Text" />
                <HstNumber v-model="state.cols" :step="1" title="colonne" />
            </template>
        </Variant>
        <!--
        <Variant title="Test1" :init-state="stateTest1" auto-props-disabled>
            <TextareaMd :id="stateTest1.id" :label="stateTest1.label" :cols="stateTest1.cols" :rows="stateTest1.rows"
                :color="stateTest1.color" v-model="stateTest1.content" />
            <template #controls></template> 
        </Variant>
    -->
    </Story>
</template>
  
<script setup>
import TextareaMd from '../components/TextareaMd.vue';

const stateDefault = () => ({
    id: "textareamd-default",
    label: "Test area par defaut",
    content: "",
    color: "red",

})

const stateTest1 = () => ({
    id: "textareamd-test1",
    label: "Test area test1",
    content: "Lorem, ipsum dolor sit amet consectetur adipisicing elit. Tempora ducimus, voluptate velit architecto facilis minima incidunt ea vero exercitationem odio blanditiis assumenda sint corporis atque voluptas delectus repellendus ex ullam!",
    color: "blue",
    cols: 32,
    rows: 3,

})

/*
const stateDefault = {
    label: "Test area par defaut",
    content: "",
    color: "red",
    id: "textareamd-default"
}

const stateTest1 = {
    label: "Test area test1",
    content: "Lorem, ipsum dolor sit amet consectetur adipisicing elit. Tempora ducimus, voluptate velit architecto facilis minima incidunt ea vero exercitationem odio blanditiis assumenda sint corporis atque voluptas delectus repellendus ex ullam!",
    color: "blue",
    cols: 32,
    rows: 3,
    id: "textareamd-test1"
}
*/
</script>

<docs lang="md">
    # Composant TextareaMd
    ## A quoi ça sert  ?
    
</docs>