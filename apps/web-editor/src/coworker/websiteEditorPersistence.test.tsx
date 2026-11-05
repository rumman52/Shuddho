import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create } from "react-test-renderer";
import { webcrypto } from "node:crypto";
import WebsiteEditor from "../../../editor/src/WebsiteEditor";
import type { CoworkerClient } from "./client";

function storageFixture() {
  const values = new Map<string,string>();
  return { values, getItem: (key:string) => values.get(key) ?? null, setItem:(key:string,value:string) => { values.set(key,value); }, removeItem:(key:string) => { values.delete(key); } };
}
const digest = async (value:string) => Array.from(new Uint8Array(await webcrypto.subtle.digest("SHA-256",new TextEncoder().encode(value))), byte => byte.toString(16).padStart(2,"0")).join("");

test("website history survives an unavailable manifest and is verified on a healthy reload", async () => {
  const previous = globalThis.sessionStorage;
  const storage = storageFixture();
  globalThis.sessionStorage = storage as unknown as Storage;
  const source="A saved website draft";
  const record={source,savedSource:source,versions:[{source,documentId:"document-1",at:"2026-11-05T00:00:00Z"}]};
  storage.setItem("rukh-website-draft:v1:alice",JSON.stringify(record));
  let tree: ReturnType<typeof create> | undefined;
  try {
    const failing={workspaceManifest:async () => { throw new Error("Temporarily unavailable"); }} as unknown as CoworkerClient;
    await act(async () => { tree=create(<WebsiteEditor client={failing} userId="alice" conversationId={null} projectId={null}/>); });
    assert.equal(JSON.parse(storage.getItem("rukh-website-draft:v1:alice")!).versions.length,1);
    assert.equal(tree!.root.findByProps({role:"status"}).children.join(""),"Unsaved draft");
    await act(async () => tree!.unmount());
    const healthy={workspaceManifest:async () => ({documents:[{document_id:"document-1",sha256:await digest(source),available:true}]})} as unknown as CoworkerClient;
    await act(async () => { tree=create(<WebsiteEditor client={healthy} userId="alice" conversationId={null} projectId={null}/>); await new Promise(resolve=>setTimeout(resolve,5)); });
    await act(async () => { await new Promise(resolve=>setTimeout(resolve,5)); });
    assert.equal(tree!.root.findByProps({role:"status"}).children.join(""),"Draft saved");
    assert.equal(JSON.parse(storage.getItem("rukh-website-draft:v1:alice")!).versions.length,1);
  } finally { if(tree) await act(async()=>tree!.unmount()); globalThis.sessionStorage=previous; }
});

test("missing or changed website backing files cannot restore Saved status", async () => {
  const previous=globalThis.sessionStorage;
  const storage=storageFixture();globalThis.sessionStorage=storage as unknown as Storage;
  storage.setItem("rukh-website-draft:v1:alice",JSON.stringify({source:"A draft",savedSource:"A draft",versions:[{source:"A draft",documentId:"gone",at:"2026-11-05T00:00:00Z"}]}));
  let tree:ReturnType<typeof create>|undefined;
  try {
    const client={workspaceManifest:async()=>({documents:[]})} as unknown as CoworkerClient;
    await act(async()=>{tree=create(<WebsiteEditor client={client} userId="alice" conversationId={null} projectId={null}/>);});
    assert.equal(tree!.root.findByProps({role:"status"}).children.join(""),"Unsaved draft");
    for(let i=0;i<100&&JSON.parse(storage.getItem("rukh-website-draft:v1:alice")!).versions.length;i++)await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1));});
    assert.deepEqual(JSON.parse(storage.getItem("rukh-website-draft:v1:alice")!).versions,[]);
  } finally {if(tree)await act(async()=>tree!.unmount());globalThis.sessionStorage=previous;}
});

test("a late website save cannot enter another account's draft or history", async () => {
  const previous=globalThis.sessionStorage;
  const storage=storageFixture();globalThis.sessionStorage=storage as unknown as Storage;
  const source="Alice confidential website source";
  storage.setItem("rukh-website-draft:v1:alice",JSON.stringify({source,savedSource:"",versions:[]}));
  const sha256=await digest(source);
  let release!: (value: {documents:unknown[]})=>void;
  const held=new Promise<{documents:unknown[]}>(resolve=>{release=resolve;});
  let calls=0;
  const alice={
    workspaceManifest:async()=>{calls++;return calls===2?held:{documents:[{document_id:"alice-file",name:"website-source.html.txt",sha256,available:true}]};},
    upload:async()=>({id:"alice-file",filename:"website-source.html.txt",state:"available",byte_size:source.length}),
    documents:async()=>({documents:[{id:"alice-file",filename:"website-source.html.txt",state:"available",byte_size:source.length}]}),
  } as unknown as CoworkerClient;
  const bob={workspaceManifest:async()=>({documents:[]})} as unknown as CoworkerClient;
  let tree:ReturnType<typeof create>|undefined;
  try {
    await act(async()=>{tree=create(<WebsiteEditor client={alice} userId="alice" conversationId={null} projectId={null}/>);});
    await act(async()=>{tree!.root.findAllByType("button").find(button=>button.children.join("")==="Save to workspace")!.props.onClick();});
    for(let i=0;i<50&&calls<2;i++)await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1));});
    assert.equal(calls,2,"save verification must be in flight before switching accounts");
    await act(async()=>{tree!.update(<WebsiteEditor client={bob} userId="bob" conversationId={null} projectId={null}/>);});
    await act(async()=>{release({documents:[]});await new Promise(resolve=>setTimeout(resolve,10));});
    assert.equal((storage.getItem("rukh-website-draft:v1:bob")??"").includes(source),false);
    assert.equal(tree!.root.findByProps({role:"status"}).children.join(""),"Unsaved draft");
  }finally{if(tree)await act(async()=>tree!.unmount());globalThis.sessionStorage=previous;}
});

test("late restoration verification cannot overwrite a newly saved website version", async () => {
  const previous=globalThis.sessionStorage;const storage=storageFixture();globalThis.sessionStorage=storage as unknown as Storage;
  const oldSource="Old website",newSource="New website";
  const oldSha=await digest(oldSource),newSha=await digest(newSource);
  storage.setItem("rukh-website-draft:v1:alice",JSON.stringify({source:oldSource,savedSource:oldSource,versions:[{source:oldSource,documentId:"old-file",at:"2026-11-05T00:00:00Z"}]}));
  let release!:(value:unknown)=>void;const initial=new Promise(resolve=>{release=resolve;});let calls=0;
  const client={workspaceManifest:async()=>{calls++;return calls===1?initial:{documents:[{document_id:"old-file",name:"website-source.html.txt",sha256:oldSha,available:true},{document_id:"new-file",name:"website-source.html.txt",sha256:newSha,available:true}]};},documents:async()=>({documents:[]}),upload:async()=>{throw new Error("exact saved source should be reused");}} as unknown as CoworkerClient;
  let tree:ReturnType<typeof create>|undefined;
  try{
    await act(async()=>{tree=create(<WebsiteEditor client={client} userId="alice" conversationId={null} projectId={null}/>);});
    await act(async()=>tree!.root.findAllByType("button").find(button=>button.children.join("")==="Code")!.props.onClick());
    await act(async()=>tree!.root.findByProps({"aria-label":"Website source"}).props.onChange({target:{value:newSource}}));
    await act(async()=>tree!.root.findAllByType("button").find(button=>button.children.join("")==="Save to workspace")!.props.onClick());
    for(let i=0;i<100&&tree!.root.findByProps({role:"status"}).children.join("")!=="Draft saved";i++)await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1));});
    assert.equal(tree!.root.findByProps({role:"status"}).children.join(""),"Draft saved");
    await act(async()=>{release({documents:[{document_id:"old-file",sha256:oldSha,available:true}]});await new Promise(resolve=>setTimeout(resolve,5));});
    const record=JSON.parse(storage.getItem("rukh-website-draft:v1:alice")!);
    assert.equal(record.savedSource,newSource);
    assert.ok(record.versions.some((item:{documentId:string})=>item.documentId==="new-file"));
    assert.equal(tree!.root.findByProps({role:"status"}).children.join(""),"Draft saved");
  }finally{if(tree)await act(async()=>tree!.unmount());globalThis.sessionStorage=previous;}
});
