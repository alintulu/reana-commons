# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA common Celery tasks."""

import logging
import importlib

from celery import shared_task
from celery.task.control import revoke
from kubernetes.client.rest import ApiException

from reana_commons.api_client import JobControllerAPIClient
from reana_commons.config import (K8S_MINIMUM_CAPACITY_CPU,
                                  K8S_MINIMUM_CAPACITY_MEMORY,
                                  K8S_MINIMUM_CAPACITY_PODS,
                                  K8S_MAXIMUM_CONCURRENT_JOBS)
from reana_commons.k8s.api_client import (current_k8s_batchv1_api_client,
                                          current_k8s_corev1_api_client)

log = logging.getLogger(__name__)


@shared_task(name='tasks.stop_workflow',
             ignore_result=True)
def stop_workflow(workflow_uuid, job_list):
    """Stop a workflow.

    :param workflow_uuid: UUID of the workflow to be stopped.
    :param job_list: List of job identifiers which where created by the given
        workflow.
    """
    rjc_api_client = JobControllerAPIClient('reana-job-controller')
    try:
        log.info('Stopping workflow {} Celery task ...'.format(workflow_uuid))
        revoke(workflow_uuid, terminate=True)
        for job_id in job_list:
            log.info('Stopping job {} from workflow {} ...'.format(
                job_id, workflow_uuid))
            response, http_response = rjc_api_client._client.jobs.delete_job(
                job_id=job_id).result()
            log.info(response)
            log.info(http_response)
    except Exception as e:
        log.error('Something went wrong while stopping workflow {} ...'.format(
            workflow_uuid
        ))
        log.error(e)


def reana_ready():
    """Check if reana can start new workflows."""
    from reana_commons.config import REANA_READY_CONDITIONS
    for module_name, condition_list in REANA_READY_CONDITIONS.items():
        for condition_name in condition_list:
            module = importlib.import_module(module_name)
            condition_func = getattr(module, condition_name)
            if not condition_func():
                return False
    return True


def check_predefined_conditions():
    """Check k8s predefined conditions for the nodes."""
    try:
        node_info = current_k8s_corev1_api_client.list_node()
        for node in node_info.items:
            # check based on the predefined conditions about the
            # node status: MemoryPressure, OutOfDisk, KubeletReady
            #              DiskPressure, PIDPressure,
            for condition in node.status.conditions:
                if not condition.status:
                    return False
    except ApiException as e:
        log.error('Something went wrong while getting node information.')
        log.error(e)
        return False
    return True


def check_running_job_count():
    """Check upper limit on running jobs."""
    try:
        job_list = current_k8s_batchv1_api_client.\
            list_job_for_all_namespaces()
        if len(job_list.items) > K8S_MAXIMUM_CONCURRENT_JOBS:
            return False
    except ApiException as e:
        log.error('Something went wrong while getting running job list.')
        log.error(e)
        return False
    return True
