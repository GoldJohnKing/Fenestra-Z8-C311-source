/* SPDX-License-Identifier: GPL-3.0-only
 * Independent schedule/ownership regression for the production inline state
 * machine plus real volume selection. Native open/close/delay are fixtures.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "cold_bootstrap.h"
#include "storage.h"
#include "fenestra_startup_service.h"
enum {CANCEL_NONE,CANCEL_STORAGE,CANCEL_LOAD,CANCEL_INSTALL,CANCEL_DELAY,CANCEL_AFTER_INSTALL};
typedef struct {
 FxColdBootstrap cold;FxZ8Storage storage;FxColdBootstrapIO io;
 uint32_t generation,cancel,cancel_at,ready_after,storage_calls,loads,installs,delays,stops,opens,closes,close_error,failed_fd;
 uint32_t publish_at_load,published,rewinds;
 FxResult storage_error,load_error,install_error,delay_error,rewind_error;
} Fixture;
static Fixture *active;static uint32_t cases;
static const FxStartupFileProfile paths={.paths={"A:\\FENESTRA\\boot-z8.flag","A:\\FENESTRA\\startup-z8.0","A:\\FENESTRA\\startup-z8.1"}};
static void duplicate(Fixture *f){
 uint32_t phase=atomic_load(&f->cold.phase),attempts=f->cold.attempts,generation=f->cold.generation;
 assert(fx_cold_bootstrap_request(&f->cold,generation)==FX_BUSY);
 assert(fx_cold_bootstrap_request(&f->cold,generation+1u)==FX_BUSY);
 assert(atomic_load(&f->cold.phase)==phase&&f->cold.attempts==attempts&&f->cold.generation==generation);
}
static uint32_t open_directory(const char *name,int32_t *fd){
 Fixture *f=active;++f->opens;assert(!strcmp(name+1,":\\FENESTRA"));
 if(f->storage_calls<f->ready_after||name[0]=='A'){
  if(f->failed_fd)*fd=77;return 0x80000010u;
 }
 assert(name[0]=='B');*fd=20;return 0;
}
static uint32_t close_directory(int32_t fd){assert(fd==20);++active->closes;return active->close_error;}
static int cancelled(void *opaque,uint32_t generation){Fixture *f=opaque;return f->cancel||generation!=f->generation;}
static FxResult storage(void *opaque){
 Fixture *f=opaque;assert(atomic_load(&f->cold.phase)==FX_COLD_WAITING);++f->storage_calls;duplicate(f);
 FxResult r=f->storage_error?f->storage_error:fx_z8_storage_select(&f->storage,open_directory,close_directory);
 if(f->cancel_at==CANCEL_STORAGE)f->cancel=1;return r;
}
static FxResult load(void *opaque){Fixture *f=opaque;assert(atomic_load(&f->cold.phase)==FX_COLD_LOADING);++f->loads;duplicate(f);if(f->publish_at_load)f->published=1;if(f->cancel_at==CANCEL_LOAD)f->cancel=1;return f->load_error;}
static FxResult install(void *opaque){
 Fixture *f=opaque;assert(atomic_load(&f->cold.phase)==FX_COLD_INSTALLING);++f->installs;duplicate(f);
 if(f->cancel_at==CANCEL_INSTALL){f->cancel=1;return FX_INTERRUPTED;}
 if(f->cancel_at==CANCEL_AFTER_INSTALL)f->cancel=1;return f->install_error;
}
static FxResult delay(void *opaque){Fixture *f=opaque;++f->delays;duplicate(f);if(f->cancel_at==CANCEL_DELAY)f->cancel=1;return f->delay_error;}
static void stop(void *opaque){Fixture *f=opaque;++f->stops;duplicate(f);}
static int published(void *opaque){return ((Fixture *)opaque)->published!=0u;}
static FxResult rewind_attempt(void *opaque){Fixture *f=opaque;assert(atomic_load(&f->cold.phase)==FX_COLD_CANCELLED&&!f->published);++f->rewinds;return f->rewind_error;}
static void init(Fixture *f){
 memset(f,0,sizeof(*f));f->generation=7;f->ready_after=3;f->io=(FxColdBootstrapIO){f,cancelled,storage,load,install,delay,stop,published,rewind_attempt};fx_z8_storage_init(&f->storage,&paths);active=f;
 assert(fx_cold_bootstrap_request(&f->cold,f->generation)==FX_OK);assert(atomic_load(&f->cold.phase)==FX_COLD_WAITING);duplicate(f);
}
static FxResult tick(Fixture *f){active=f;return fx_cold_bootstrap_step(&f->cold,&f->io);}
static void terminal(Fixture *f,uint32_t phase,FxResult result){
 assert(atomic_load(&f->cold.phase)==phase&&atomic_load(&f->cold.error)==(uint32_t)result);uint32_t calls=f->storage_calls,loads=f->loads,installs=f->installs,opens=f->opens;
 duplicate(f);assert(tick(f)==FX_STATE);duplicate(f);assert(f->storage_calls==calls&&f->loads==loads&&f->installs==installs&&f->opens==opens);++cases;
}

/* This invokes the production owner loop, not a copied test-side retry loop. */
static void owner_loop_results(void) {
 Fixture f;
 init(&f);assert(fx_cold_bootstrap_run(&f.cold,&f.io)==FX_OK);
 assert(f.cold.attempts==3u&&f.delays==2u&&f.loads==1u&&f.installs==1u);terminal(&f,FX_COLD_READY,FX_OK);
 init(&f);f.storage_error=FX_BUSY;assert(fx_cold_bootstrap_run(&f.cold,&f.io)==FX_BUSY);
 assert(f.storage_calls==1u&&!f.delays&&!f.loads);terminal(&f,FX_COLD_FAILED,FX_BUSY);
 init(&f);f.ready_after=1u;f.load_error=FX_BUSY;assert(fx_cold_bootstrap_run(&f.cold,&f.io)==FX_BUSY);
 assert(f.loads==1u&&f.stops==1u&&!f.installs);terminal(&f,FX_COLD_FAILED,FX_BUSY);
 init(&f);f.ready_after=1u;f.install_error=FX_BUSY;assert(fx_cold_bootstrap_run(&f.cold,&f.io)==FX_BUSY);
 assert(f.installs==1u&&f.stops==1u);terminal(&f,FX_COLD_FAILED,FX_BUSY);
 init(&f);f.delay_error=FX_BUSY;assert(fx_cold_bootstrap_run(&f.cold,&f.io)==FX_BUSY);
 assert(f.storage_calls==1u&&f.delays==1u&&!f.loads);terminal(&f,FX_COLD_FAILED,FX_BUSY);
 init(&f);f.ready_after=101u;assert(fx_cold_bootstrap_run(&f.cold,&f.io)==FX_TIMEOUT);
 assert(f.cold.attempts==100u&&f.delays==99u&&!f.loads);terminal(&f,FX_COLD_FAILED,FX_TIMEOUT);
}
typedef struct {uint32_t stops,activation,health,token,reads,creates,removes,retires;} StopFixture;
static FxResult service_activate(void *p){++((StopFixture *)p)->activation;return FX_OK;}
static FxResult service_health(void *p){++((StopFixture *)p)->health;return FX_OK;}
static uint64_t service_token(void *p){++((StopFixture *)p)->token;return 1u;}
static FxResult service_stop(void *p){return ++((StopFixture *)p)->stops==1u?FX_BUSY:FX_OK;}
static FxResult service_retire(void *p){return ++((StopFixture *)p)->retires==1u?FX_BUSY:FX_OK;}
static FxResult service_read(void *p,uint32_t id,uint8_t *out,uint32_t cap,uint32_t *n){(void)id;(void)out;(void)cap;(void)n;++((StopFixture *)p)->reads;return FX_IO;}
static FxResult service_create(void *p,uint32_t id,const uint8_t *data,uint32_t n){(void)id;(void)data;(void)n;++((StopFixture *)p)->creates;return FX_IO;}
static FxResult service_remove(void *p,uint32_t id){(void)id;++((StopFixture *)p)->removes;return FX_IO;}
static void waiting_shutdown_ack(void) {
 Fixture f;StopFixture stop={0};FxStartupService startup;
 init(&f);assert(tick(&f)==FX_BUSY);assert(!f.loads&&!f.installs);
 fx_startup_service_init(&startup,0x00080311u,(FxStartupBackend){&stop,service_activate,service_health,service_stop,service_token,0});
 startup.io=(FxStartupIO){&stop,service_read,service_create,service_remove};
 startup.journal.desired=FX_STARTUP_AUTO|FX_STARTUP_DEMO;
 assert(fx_startup_service_request(&startup,FX_START_ACTIVATE)==FX_OK);
 atomic_store(&startup.inspect_requested,1u);atomic_store(&startup.cleanup_window,1u);atomic_store(&startup.shutdown,1u);f.cancel=1u;
 assert(tick(&f)==FX_INTERRUPTED);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
 fx_startup_service_tick(&startup);assert(stop.stops==1u&&!atomic_load(&startup.shutdown_done));
 fx_startup_service_tick(&startup);assert(stop.stops==2u&&atomic_load(&startup.shutdown_done));
 atomic_store(&startup.cleanup_window,0u);fx_startup_service_tick(&startup);assert(stop.stops==2u);
 assert(fx_startup_service_request(&startup,FX_START_ACTIVATE)==FX_STATE);
 assert(!stop.activation&&!stop.health&&!stop.token&&!stop.reads&&!stop.creates&&!stop.removes);
 assert(!f.loads&&!f.installs&&f.storage_calls==1u&&f.delays==1u);
}

/* Retire runs only after stop OK, never before; its BUSY withholds done. */
static void retire_after_stop(void) {
 StopFixture stop={0};FxStartupService startup;
 fx_startup_service_init(&startup,0x00080311u,(FxStartupBackend){&stop,service_activate,service_health,service_stop,service_token,service_retire});
 startup.io=(FxStartupIO){&stop,service_read,service_create,service_remove};
 atomic_store(&startup.cleanup_window,1u);atomic_store(&startup.shutdown,1u);
 fx_startup_service_tick(&startup);assert(stop.stops==1u&&!stop.retires&&!atomic_load(&startup.shutdown_done));
 fx_startup_service_tick(&startup);assert(stop.stops==2u&&stop.retires==1u&&!atomic_load(&startup.shutdown_done));
 fx_startup_service_tick(&startup);assert(stop.stops==3u&&stop.retires==2u&&atomic_load(&startup.shutdown_done));
 fx_startup_service_tick(&startup);assert(stop.stops==3u&&stop.retires==2u);
}

/* Published native state never ends restartable: a cancelled shutdown can
 * only meet it as READY (normal stop/resume) or a terminal failure. */
static void published_attempts(void) {
 Fixture f;
 init(&f);f.ready_after=1u;f.publish_at_load=1u;f.cancel_at=CANCEL_LOAD;assert(tick(&f)==FX_OK);
 assert(f.loads==1u&&f.installs==1u&&!f.stops&&f.cancel);terminal(&f,FX_COLD_READY,FX_OK);
 init(&f);f.ready_after=1u;f.publish_at_load=1u;f.cancel_at=CANCEL_LOAD;f.load_error=FX_INTERRUPTED;assert(tick(&f)==FX_INTERRUPTED);
 assert(f.loads==1u&&!f.installs&&f.stops==1u);terminal(&f,FX_COLD_FAILED,FX_INTERRUPTED);
 init(&f);f.ready_after=1u;f.publish_at_load=1u;f.load_error=FX_INTEGRITY;assert(tick(&f)==FX_INTEGRITY);
 assert(f.stops==1u&&!f.installs);terminal(&f,FX_COLD_FAILED,FX_INTEGRITY);
 init(&f);f.ready_after=1u;f.publish_at_load=1u;f.cancel_at=CANCEL_INSTALL;assert(tick(&f)==FX_INTERRUPTED);
 assert(f.installs==1u&&f.stops==1u);terminal(&f,FX_COLD_FAILED,FX_INTERRUPTED);
 FxColdBootstrapIO missing=f.io;missing.published=0;FxColdBootstrap c={0};assert(fx_cold_bootstrap_request(&c,1u)==FX_OK);
 assert(fx_cold_bootstrap_step(&c,&missing)==FX_ARGUMENT);missing=f.io;missing.rewind=0;assert(fx_cold_bootstrap_step(&c,&missing)==FX_ARGUMENT);
 assert(atomic_load(&c.phase)==FX_COLD_WAITING);
 const FxResult real[]={FX_BUDGET,FX_IO,FX_INTEGRITY,FX_STATE};
 for(uint32_t i=0u;i<sizeof(real)/sizeof(real[0]);++i){init(&f);f.ready_after=1u;f.cancel_at=CANCEL_LOAD;f.load_error=real[i];
  assert(tick(&f)==real[i]&&f.stops==1u&&!f.installs);terminal(&f,FX_COLD_FAILED,real[i]);}
 init(&f);f.ready_after=1u;f.cancel_at=CANCEL_LOAD;f.load_error=FX_INTERRUPTED;assert(tick(&f)==FX_INTERRUPTED);
 assert(f.stops==1u);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
}
static void cancel_load(Fixture *f){
 f->ready_after=0u;f->cancel_at=CANCEL_LOAD;assert(tick(f)==FX_INTERRUPTED);assert(atomic_load(&f->cold.phase)==FX_COLD_CANCELLED);
}
/* Only CANCELLED continues, under a fresh generation, after rewind, bounded. */
static void retries(void) {
 Fixture f;init(&f);cancel_load(&f);
 assert(fx_cold_bootstrap_retry(&f.cold,&f.io,f.generation)==FX_ARGUMENT);
 assert(fx_cold_bootstrap_retry(&f.cold,&f.io,0u)==FX_ARGUMENT&&fx_cold_bootstrap_retry(0,&f.io,9u)==FX_ARGUMENT);
 FxColdBootstrapIO missing=f.io;missing.rewind=0;assert(fx_cold_bootstrap_retry(&f.cold,&missing,9u)==FX_ARGUMENT);
 assert(!f.rewinds&&atomic_load(&f.cold.phase)==FX_COLD_CANCELLED&&!f.cold.retries);
 uint32_t loads=f.loads;f.generation=8u;f.cancel=0u;f.cancel_at=CANCEL_NONE;
 assert(fx_cold_bootstrap_retry(&f.cold,&f.io,8u)==FX_OK);
 assert(f.rewinds==1u&&f.cold.retries==1u&&f.cold.generation==8u&&!f.cold.attempts&&atomic_load(&f.cold.error)==FX_OK);
 assert(atomic_load(&f.cold.phase)==FX_COLD_WAITING);duplicate(&f);
 assert(fx_cold_bootstrap_run(&f.cold,&f.io)==FX_OK&&f.loads==loads+1u);terminal(&f,FX_COLD_READY,FX_OK);
 assert(fx_cold_bootstrap_retry(&f.cold,&f.io,9u)==FX_STATE&&f.rewinds==1u);
 init(&f);f.ready_after=1u;f.load_error=FX_BUDGET;assert(tick(&f)==FX_BUDGET);
 assert(fx_cold_bootstrap_retry(&f.cold,&f.io,9u)==FX_STATE&&!f.rewinds);terminal(&f,FX_COLD_FAILED,FX_BUDGET);
 init(&f);assert(fx_cold_bootstrap_retry(&f.cold,&f.io,9u)==FX_STATE&&!f.rewinds);
 init(&f);
 for(uint32_t i=0u;i<FX_COLD_BOOTSTRAP_RETRIES;++i){
  cancel_load(&f);f.generation=9u+i;f.cancel=0u;assert(fx_cold_bootstrap_retry(&f.cold,&f.io,f.generation)==FX_OK);
 }
 cancel_load(&f);assert(f.cold.retries==FX_COLD_BOOTSTRAP_RETRIES&&f.rewinds==FX_COLD_BOOTSTRAP_RETRIES);
 assert(fx_cold_bootstrap_retry(&f.cold,&f.io,99u)==FX_BOUNDS);
 assert(f.rewinds==FX_COLD_BOOTSTRAP_RETRIES);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
 init(&f);cancel_load(&f);f.rewind_error=FX_STATE;assert(fx_cold_bootstrap_retry(&f.cold,&f.io,9u)==FX_STATE);
 assert(f.rewinds==1u&&!f.cold.retries&&f.cold.generation==7u);terminal(&f,FX_COLD_FAILED,FX_STATE);
}

int main(void){
 Fixture f;
 init(&f);assert(tick(&f)==FX_BUSY&&f.delays==1);duplicate(&f);assert(tick(&f)==FX_BUSY&&f.delays==2);assert(tick(&f)==FX_OK);assert(f.loads==1&&f.installs==1&&!f.stops&&f.opens==6&&f.closes==1&&fx_z8_storage_drive(&f.storage)=='B');terminal(&f,FX_COLD_READY,FX_OK);
 init(&f);f.ready_after=101;for(uint32_t i=0;i<99;++i)assert(tick(&f)==FX_BUSY);assert(tick(&f)==FX_TIMEOUT);assert(f.cold.attempts==100&&f.storage.attempts==100&&f.storage_calls==100&&f.delays==99&&f.opens==200&&!f.loads&&!f.installs&&!f.stops);terminal(&f,FX_COLD_FAILED,FX_TIMEOUT);
 init(&f);f.ready_after=100;for(uint32_t i=0;i<99;++i)assert(tick(&f)==FX_BUSY);assert(tick(&f)==FX_OK);assert(f.cold.attempts==100&&f.storage.attempts==100&&f.delays==99&&f.loads==1&&f.installs==1);terminal(&f,FX_COLD_READY,FX_OK);
 init(&f);f.cancel=1;assert(tick(&f)==FX_INTERRUPTED);assert(!f.storage_calls&&!f.opens&&!f.loads&&!f.installs&&!f.stops);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
 init(&f);f.generation=8;assert(tick(&f)==FX_INTERRUPTED);assert(!f.storage_calls);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
 init(&f);f.cancel_at=CANCEL_STORAGE;assert(tick(&f)==FX_INTERRUPTED);assert(f.storage_calls==1&&!f.delays&&!f.loads&&!f.installs&&!f.stops);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
 init(&f);f.cancel_at=CANCEL_DELAY;assert(tick(&f)==FX_BUSY);assert(f.storage_calls==1&&f.delays==1);assert(tick(&f)==FX_INTERRUPTED);assert(f.storage_calls==1&&!f.loads);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
 init(&f);f.ready_after=1;f.close_error=0x80000005u;assert(tick(&f)==FX_CLOSE);assert(f.opens==2&&f.closes==1&&f.storage.latched_error==FX_CLOSE&&!f.loads&&!f.installs);terminal(&f,FX_COLD_FAILED,FX_CLOSE);
 init(&f);f.failed_fd=1;assert(tick(&f)==FX_CLOSE);assert(f.opens==1&&!f.closes&&f.storage.latched_error==FX_CLOSE&&!f.loads);terminal(&f,FX_COLD_FAILED,FX_CLOSE);
 init(&f);f.ready_after=1;f.close_error=0x80000005u;f.cancel_at=CANCEL_STORAGE;assert(tick(&f)==FX_CLOSE);assert(f.storage.latched_error==FX_CLOSE&&!f.loads);terminal(&f,FX_COLD_FAILED,FX_CLOSE);
 const FxResult nonretry[]={FX_BUSY,FX_BUDGET,FX_INTEGRITY,FX_STATE};
 for(uint32_t i=0;i<sizeof(nonretry)/sizeof(nonretry[0]);++i){init(&f);f.storage_error=nonretry[i];assert(tick(&f)==nonretry[i]);assert(f.storage_calls==1&&!f.delays&&!f.loads);terminal(&f,FX_COLD_FAILED,nonretry[i]);}
 init(&f);f.delay_error=FX_IO;assert(tick(&f)==FX_IO);assert(f.storage_calls==1&&f.delays==1&&!f.loads);terminal(&f,FX_COLD_FAILED,FX_IO);
 const FxResult loadfail[]={FX_IO,FX_CLOSE,FX_BUDGET,FX_BUSY};
 for(uint32_t i=0;i<sizeof(loadfail)/sizeof(loadfail[0]);++i){init(&f);f.ready_after=1;f.load_error=loadfail[i];assert(tick(&f)==loadfail[i]);assert(f.loads==1&&!f.installs&&f.stops==1&&!f.delays);terminal(&f,FX_COLD_FAILED,loadfail[i]);}
 init(&f);f.ready_after=1;f.load_error=FX_CLOSE;f.cancel_at=CANCEL_LOAD;assert(tick(&f)==FX_CLOSE);assert(f.loads==1&&!f.installs&&f.stops==1);terminal(&f,FX_COLD_FAILED,FX_CLOSE);
 init(&f);f.ready_after=1;f.cancel_at=CANCEL_LOAD;assert(tick(&f)==FX_INTERRUPTED);assert(f.loads==1&&!f.installs&&f.stops==1);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
 init(&f);f.ready_after=1;f.cancel_at=CANCEL_INSTALL;assert(tick(&f)==FX_INTERRUPTED);assert(f.loads==1&&f.installs==1&&f.stops==1);terminal(&f,FX_COLD_CANCELLED,FX_INTERRUPTED);
 init(&f);f.ready_after=1;f.install_error=FX_BUDGET;assert(tick(&f)==FX_BUDGET);assert(f.installs==1&&f.stops==1);terminal(&f,FX_COLD_FAILED,FX_BUDGET);
 init(&f);f.ready_after=1;f.cancel_at=CANCEL_AFTER_INSTALL;assert(tick(&f)==FX_OK);assert(f.installs==1&&!f.stops&&f.cancel);terminal(&f,FX_COLD_READY,FX_OK); /* normal runtime stop now owns cancellation */
 assert(fx_cold_bootstrap_request(0,1)==FX_ARGUMENT);FxColdBootstrap empty={0};assert(fx_cold_bootstrap_request(&empty,0)==FX_ARGUMENT);assert(fx_cold_bootstrap_step(&empty,0)==FX_ARGUMENT);assert(atomic_load(&empty.phase)==FX_COLD_EMPTY);
 owner_loop_results();waiting_shutdown_ack();retire_after_stop();published_attempts();retries();
 printf("PASS: %u production bootstrap schedules, bounded retries, ownership, generation and duplicate events; owner-loop terminal BUSY and waiting shutdown ACK; published never restartable; real errors terminal; bounded rewind-first continuation\n",cases);return 0;
}
