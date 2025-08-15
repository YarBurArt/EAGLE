$(document).ready( () => {
    // TODO: remove jQuery
    $.ajaxSetup({timeout:600000}); // 10m
    var accessToken = '';
    var refreshToken = '';
    var accessTokenExpiresAt = 0;
    var refreshTokenExpiresAt = 0;
    var currentChainId = null;
    var chainWebSocket = null;
    var baseURL = 'http://localhost:8000';
    // cuz cors policy
    var myOrigin = 'http://127.0.0.1:8000';
    // var currentController = null;

    $('#loginForm').on('submit', e => {
        e.preventDefault();

        var formData = new FormData();
        formData.append('username', $('#email').val());
        formData.append('password', $('#password').val());
        // get JWT access token by post with email/password 
        $.post({
            url: `${baseURL}/auth/access-token`, 
            data: formData,
            processData: false, contentType: false,
        }).done( res => {   // set as global var if correct
            accessToken = res.access_token;
            refreshToken = res.refresh_token;
            accessTokenExpiresAt = res.expires_at;
            refreshTokenExpiresAt = res.refresh_token_expires_at;
            // show user forms of agent/chain control
            $('#loginForm').hide();
            $('#commandForm').show();
            $('#agentCommandForm').show();
            $('#runChainForm').show();
            $('#emergencyCancelBtn').show();
            $('#result').html('Logged in successfully!');
        }).fail( (xhr, status, error) => {  // show error like invalid creds
            $('#result').html('Login Error: ' + xhr.responseText);
            }
        );
    });

    $('#commandForm').on('submit', e => {
        e.preventDefault();
        // for data serialization JSON, and this is understood by pydantic on the other side
        var requestData = {
            chain_name: $('#chainName').val(),
            command: $('#command').val(),
            callback_display_id: $('#callbackDisplayId').val()
        };

        $.ajax({
            url: `${baseURL}/cmd/run-command`, 
            type: 'POST',
            contentType: 'application/json',
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Origin': myOrigin
            },
            data: JSON.stringify(requestData),
        }).done( response => {
            $('#result').html('Command Success: ' + JSON.stringify(response));
        }).fail( (xhr, status, error) => {
            $('#result').html('Command Error: ' + xhr.responseText);
        });
    });
    $('#agentCommandForm').on('submit', e => {
        e.preventDefault();

        var requestData = {
            chain_name: $('#chainName').val(),
            command: $('#command').val(),
            tool: $('#tool').val(),  
            callback_display_id: $('#callbackDisplayId').val()
        };
        // ajax cuz it's more interesting
        $.ajax({
            url: `${baseURL}/cmd/run-agent-command`, 
            type: 'POST',
            contentType: 'application/json',
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Origin': myOrigin
            },
            data: JSON.stringify(requestData),
        }).done( response => {
            $('#result').html('Command Success: ' + JSON.stringify(response));
        }).fail( (xhr, status, error) => {
            $('#result').html('Command Error: ' + xhr.responseText);
        });
    });
    $('#runChainForm').on('submit', async e => {
        e.preventDefault();
        var chainId = $('#chainId').val();
        var zeroDisplayId = $('#zeroDisplayId').val();

        $('#result').html('Run chain ...');
        $('#chainOutput').empty();

        try {
            // for advanced http stream timeout control
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60 * 60 * 1000);

            const response = await fetch(
                `${baseURL}/cmd/run-chain/${chainId}?zero_display_id=${zeroDisplayId}`, {
                method: 'POST',
                headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`,
                'Origin': myOrigin
                },
                body: JSON.stringify({ zero_display_id: zeroDisplayId }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(await response.text());
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let done = false;

            while (!done) {
                // until the stream is done
                const { value, done: streamDone } = await reader.read();
                done = streamDone;
                if (value) {
                    const chunk = decoder.decode(value, { stream: true });
                    chunk.split('\n').forEach(line => {
                        // we output the result line by line in each http chunk
                        if (line.trim()) {
                            try {
                                const json = JSON.parse(line);
                                $('#chainOutput').append(`<p>${JSON.stringify(json)}</p>`);
                            } catch {
                                console.warn('JSON:', line);
                            }
                        }
                    });
                }
            }

            $('#result').html('Chain is done');
        } catch (err) {
            if (err.name === 'AbortError') {
                $('#result').html('timeout, check server');
            } else {
                $('#result').html('Error run chain: ' + err.message);
            }
        }

        setupCancelWebSocket(chainId);
    });

    const setupCancelWebSocket = chainId => {
        // open new web socket for chain cancel
        if (chainWebSocket) {
            chainWebSocket.close();
        }

        chainWebSocket = new WebSocket(
            `ws://localhost:8000/cmd/ws/cancel-chain/${chainId}`
        );

        chainWebSocket.onopen = () => 
            console.log('WebSocket for cancel chain is set');

        chainWebSocket.onerror = error =>
            console.error('Error WebSocket:', error);
    }
    $('#emergencyCancelBtn').on('click', async () => {
        // try http and WS methods cuz async fastapi, it works but not for the current step
        console.log($('#chainName').val());
        var chainName = $('#chainName').val();
        var chainId = $('#chainId').val();
        await fetch(
            `${baseURL}/cmd/cancel-chain/${chainId}?chain_name=${chainName}`, {
            method: 'POST',
            headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${accessToken}`,
            'Origin': myOrigin
            },
            body: JSON.stringify({ chain_name: chainName }),
        }).then( res => {
            $('#result').html('Cancel chain...');
            $('#chainOutput').append(
                `<p style="color: red;">${res}</p>`);
            }
        ).catch( err => {
            console.error(`cant cancel because ${err}`);
            $('#result').html(
                'WebSocket cant connect for cancel, you must stop via cli');
        });
        // it finishes the current step anyway and one of the methods is triggered every other time
        if (currentChainId && chainWebSocket) {
            if (chainWebSocket.readyState === WebSocket.OPEN) {
                // send to WS chain name as temp auth check
                chainWebSocket.send(chainName);
                
                $('#result').html('Cancel chain...');
                $('#chainOutput').append(
                    '<p style="color: red;">STOP CHAIN</p>');
            } else {
                console.error('WebSocket cant connect');
                $('#result').html(
                    'WebSocket cant connect for cancel, you must stop via cli');
            } 
        } else {
            $('#result').html('No active chain at now');
        }
    });

    chainWebSocket.onclose = () => {
        console.log('WebSocket closed');
        $('#result').append('<p>WebSocket closed</p>');
    };
});
