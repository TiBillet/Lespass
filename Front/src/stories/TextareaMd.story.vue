<template>
    <Story title="components/TextareaMd">
        <Variant title="Default" :init-state="stateDefault" auto-props-disabled>
            <template #default="{ state }">
                <TextareaMd id="textareamd-default" :label="state.label" :color="state.color" v-model:content="state.content" />
            </template>
            <template #controls="{ state }">
                <HstTextarea v-model="state.content" title="Text" />
                <HstNumber v-model="state.cols" :step="1" title="colonne" />
            </template>

        </Variant>
        <Variant title="Test1" :init-state="stateTest1" auto-props-disabled>
            <template #default="{ state }">
                <TextareaMd id="textareamd-test1" :label="state.label" :cols="state.cols" :rows="state.rows" :color="state.color"
                    v-model:content="state.content" />
            </template>
            <template #controls="{ state }">
                <HstTextarea v-model="state.content" title="Text" />
                <HstNumber v-model="state.cols" :step="1" title="colonne" />
            </template>
        </Variant>

    </Story>
</template>
  
<script setup>
import TextareaMd from '../components/TextareaMd.vue';

const stateDefault = () => ({
    label: "Test area par defaut",
    content: "",
    color: "red",

})

const stateTest1 = () => ({
    label: "Test area test1",
    content: "Lorem, ipsum dolor sit amet consectetur adipisicing elit. Tempora ducimus, voluptate velit architecto facilis minima incidunt ea vero exercitationem odio blanditiis assumenda sint corporis atque voluptas delectus repellendus ex ullam!",
    color: "blue",
    cols: 32,
    rows: 3,

})
</script>

<docs lang="md">
    # Composant TextareaMd
    ## A quoi ça sert  ?
    
</docs>