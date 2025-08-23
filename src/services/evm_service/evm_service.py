import asyncio
import json
import os
import threading
import time
import traceback
import grpc
from protos.analyzer import bytecode_analyzer_pb2
from protos.analyzer import evm_engine_pb2_grpc
from analyzers import solidity_bin as analyzer
from utils import global_params, context, log, util

cfg = util.get_config('./config.yaml')

log.mylogger = log.get_logger('evm')
# TODO(Yang): z3-solver will fail for concurrent calls to EvmEngineService
lock = threading.Lock()


class EvmEngineService(evm_engine_pb2_grpc.EVMEngineServicer):

    def AnalyseByteCode(
            self, request: bytecode_analyzer_pb2.ByteCodeAnalysisRequest,
            unused_context) -> bytecode_analyzer_pb2.ByteCodeAnalysisResponse:
        request_id = str(int(time.time() * 1000000))
        log.mylogger.info('waiting for request %s, project: %s, file: %s',
                          request_id, request.before_change.repo_path,
                          request.before_change.file_path)

        # wait for other request end
        with lock:
            # start processing request
            # 1. before commit, i.e. parent
            start = time.time()
            project_name = "Default"
            output_path = util.generate_output_dir(request_id,
                                                   'bytecode_before')
            src_path = request.before_change.file_path
            project_path = os.path.join(
                global_params.INPUT_PATH,
                util.change_to_relative(request.before_change.repo_path))
            diff_path = os.path.join(
                global_params.INPUT_PATH,
                util.change_to_relative(request.diffs_log_path))
            log.mylogger.info(
                'starting process request %s for commit before, '
                'project: %s, file: %s', request_id, project_path, src_path)

            diff = util.get_diff(diff_path, True)
            context_before = context.Context(start, project_path, src_path,
                                             diff, '', request_id)
            try:
                cfg_b, ssg_b = analyzer.analyze_evm_from_solidity(
                    output_path, src_path, project_path, context_before, cfg['compilation'][project_name])
            except Exception as err:  # pylint: disable=broad-except
                traceback.print_exc()
                context_before.set_err(context.ExecErrorType.SYMBOL_EXEC)
                log.mylogger.error(
                    'fail analyzing evm bytecode before for request: %s, file: %s, err: %s',
                    request_id, src_path, str(err))
                return bytecode_analyzer_pb2.ByteCodeAnalysisResponse(
                    status=500, message='analysis evm before file error')

            # 2. after commit, i.e. child
            start = time.time()
            output_path = util.generate_output_dir(request_id, 'bytecode_after')
            src_path = request.after_change.file_path
            project_path = os.path.join(
                global_params.INPUT_PATH,
                util.change_to_relative(request.after_change.repo_path))
            log.mylogger.info(
                'starting processing request %s for commit after, '
                'project: %s, file: %s', request_id, project_path, src_path)
            diff = util.get_diff(diff_path, False)
            context_after = context.Context(start, project_path, src_path, diff,
                                            '', request_id)
            try:
                cfg_a, ssg_a = analyzer.analyze_evm_from_solidity(
                    output_path, src_path, project_path, context_after, cfg['compilation'][project_name])
            except Exception as err:  # pylint: disable=broad-except
                traceback.print_exc()
                context_after.set_err(context.ExecErrorType.SYMBOL_EXEC)
                log.mylogger.error(
                    'fail analyzing evm bytecode after for request: %s, file: %s, err: %s',
                    request_id, src_path, str(err))
                return bytecode_analyzer_pb2.ByteCodeAnalysisResponse(
                    status=500, message='analysis evm after file error')

            # merge before's and after's cfg abstarct
            try:
                output_path = util.generate_output_dir(request_id, '')
                cfg_abstract = {}
                # TODO(Chao): Use `zip` function instead
                for index in cfg_a.cfg_abstract:
                    if not context_before.err and not context_after.err:
                        if context_before.is_index_err(index) or context_after.is_index_err(index):
                            cfg_abstract[index] = 0
                        else:
                            cfg_abstract[index] = cfg_a.cfg_abstract[
                                                      index] - cfg_b.cfg_abstract[index]
                    else:
                        cfg_abstract[index] = 0
                cfg_abstract_path = os.path.join(output_path,
                                                 'cfg_abstract.json')
                with open(cfg_abstract_path, 'w',
                          encoding='utf8') as output_file:
                    json.dump(cfg_abstract, output_file)
            except Exception as err:  # pylint: disable=broad-except
                traceback.print_exc()
                log.mylogger.error('fail merge cfg abstract for request: %s, err: %s', request_id, str(err))
                return bytecode_analyzer_pb2.ByteCodeAnalysisResponse(
                    status=500, message='merge cfg abstract fail')

            # merge before's and after's ssg abstarct
            try:
                output_path = util.generate_output_dir(request_id, '')
                ssg_abstract = {}
                # TODO(Chao): Use `zip` function instead
                for index in ssg_a.ssg_abstract:
                    if not context_before.err and not context_after.err:
                        if context_before.is_index_err(index) or context_after.is_index_err(index):
                            ssg_abstract[index] = 0
                        else:
                            ssg_abstract[index] = ssg_a.ssg_abstract[
                                                      index] - ssg_b.ssg_abstract[index]
                    else:
                        ssg_abstract[index] = 0
                ssg_abstract_path = os.path.join(output_path,
                                                 'ssg_abstract.json')
                with open(ssg_abstract_path, 'w',
                          encoding='utf8') as output_file:
                    json.dump(ssg_abstract, output_file)
            except Exception as err:  # pylint: disable=broad-except
                traceback.print_exc()
                log.mylogger.error('fail merge ssg abstract for request: %s, err: %s', request_id, str(err))
                return bytecode_analyzer_pb2.ByteCodeAnalysisResponse(
                    status=500, message='merge ssg abstract fail')

            log.mylogger.info('success analyzing request %s, result in %s ',
                              request_id, output_path)
            return bytecode_analyzer_pb2.ByteCodeAnalysisResponse(
                status=200,
                message='solidity analysis result',
                cfg_before_path=util.change_to_relative(
                    util.remove_prefix(cfg_b.cfg_json_path,
                                       global_params.DEST_PATH)),
                cfg_after_path=util.change_to_relative(
                    util.remove_prefix(cfg_a.cfg_json_path,
                                       global_params.DEST_PATH)),
                ssg_before_path=util.change_to_relative(
                    util.remove_prefix(ssg_b.ssg_json_path,
                                       global_params.DEST_PATH)),
                ssg_after_path=util.change_to_relative(
                    util.remove_prefix(ssg_a.ssg_json_path,
                                       global_params.DEST_PATH)),
                cfg_abstract_path=util.change_to_relative(
                    util.remove_prefix(cfg_abstract_path,
                                       global_params.DEST_PATH)),
                ssg_abstract_path=util.change_to_relative(
                    util.remove_prefix(ssg_abstract_path,
                                       global_params.DEST_PATH)),
                cfg_edge_lists_before_path=util.change_to_relative(
                    util.remove_prefix(cfg_b.cfg_edge_lists_path,
                                       global_params.DEST_PATH)),
                cfg_edge_lists_after_path=util.change_to_relative(
                    util.remove_prefix(cfg_a.cfg_edge_lists_path,
                                       global_params.DEST_PATH)),
                ssg_edge_lists_before_path=util.change_to_relative(
                    util.remove_prefix(ssg_b.ssg_edge_lists_path,
                                       global_params.DEST_PATH)),
                ssg_edge_lists_after_path=util.change_to_relative(
                    util.remove_prefix(ssg_a.ssg_edge_lists_path,
                                       global_params.DEST_PATH)),
            )


async def serve(address) -> None:
    server = grpc.aio.server()
    evm_engine_pb2_grpc.add_EVMEngineServicer_to_server(EvmEngineService(),
                                                        server)
    server.add_insecure_port(address)
    log.mylogger.info('EVM Engine Service is Listening on %s...', address)

    await server.start()
    await server.wait_for_termination()


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(serve(cfg['listen_address']))
